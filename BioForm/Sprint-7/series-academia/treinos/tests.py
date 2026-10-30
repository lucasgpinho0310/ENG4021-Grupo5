import io
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from metas.calculo import salvar_meta
from saude.models import ExercicioFicha, FichaTreino, HistoricoMedida, Usuario

from . import servicos
from .leitor import ler_intervalo, ler_series, ler_series_por_tempo, ler_texto
from .templatetags.treinos_tags import carga, intervalo, series_de, video_embed

User = get_user_model()
SENHA = 'treino-forte-2026'
MIDIA_DE_TESTE = tempfile.mkdtemp()

INFERIORES = """Mobilidade SacroLombar em 4 Apoios
Séries: 1/10
Carga:  0kg

SAMURAI OMBRO
Séries: 1/10
Carga:  0kg

Core na Polia Rotação - Base unilateral
Séries: 3/10 cada lado
Carga:  0kg
Intervalo: 60s

Exercícios combinados
Alterne esses exercícios
Afundo Unilateral
A

Agachamento Frontal com Halter
B
Séries: 3x10+10
Carga:  0kg
Intervalo: 120s
Instruções:
Mesma carga e reps em todas as séries

Adução de Quadril na Polia Unilateral
Séries: 3/10
Carga:  10kg
Intervalo: 45s

Cadeira Extensora
Séries: 3x15
Carga:  0kg
Intervalo: 60s

Cadeira Flexora Unilateral
Séries: 3x10
Carga:  0kg
Intervalo: 60s

Abdução de Quadril Máquina
Séries: 3x10
Carga:  0kg
Intervalo: 60s
Instruções:
Última série até não conseguir mais

Panturrilha Sentado Maquina
Séries: 3/15
Carga:  15 kg
Intervalo: 40s
"""


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


def imagem_png(nome='aparelho.png'):
    arquivo = io.BytesIO()
    Image.new('RGB', (20, 20), (255, 87, 34)).save(arquivo, 'PNG')
    return SimpleUploadedFile(nome, arquivo.getvalue(), content_type='image/png')


class LeitorTest(TestCase):
    def test_serie_de_inferiores_tem_10_exercicios(self):
        leitura = ler_texto(INFERIORES)
        self.assertEqual(len(leitura.exercicios), 10)
        self.assertEqual(leitura.combinados, 1)
        self.assertEqual(leitura.avisos, [])
        nomes = [e.nome for e in leitura.exercicios]
        self.assertEqual(nomes[0], 'Mobilidade SacroLombar em 4 Apoios')
        self.assertEqual(nomes[-1], 'Panturrilha Sentado Maquina')

    def test_campos_de_cada_exercicio(self):
        e = {x.nome: x for x in ler_texto(INFERIORES).exercicios}
        mobilidade = e['Mobilidade SacroLombar em 4 Apoios']
        self.assertEqual((mobilidade.series, mobilidade.repeticoes), (1, 10))
        core = e['Core na Polia Rotação - Base unilateral']
        self.assertTrue(core.cada_lado)
        self.assertEqual(core.intervalo_segundos, 60)
        aducao = e['Adução de Quadril na Polia Unilateral']
        self.assertEqual(aducao.carga_kg, Decimal('10'))
        self.assertEqual(e['Panturrilha Sentado Maquina'].carga_kg, Decimal('15'))
        self.assertEqual(e['Abdução de Quadril Máquina'].instrucoes, 'Última série até não conseguir mais')

    def test_combinados_dividem_series_e_intervalo(self):
        e = {x.nome: x for x in ler_texto(INFERIORES).exercicios}
        afundo, agachamento = e['Afundo Unilateral'], e['Agachamento Frontal com Halter']
        self.assertEqual((afundo.letra, agachamento.letra), ('A', 'B'))
        self.assertFalse(afundo.combinado_com_anterior)
        self.assertTrue(agachamento.combinado_com_anterior)
        for exercicio in (afundo, agachamento):
            self.assertEqual((exercicio.series, exercicio.repeticoes), (3, 10))
            self.assertEqual(exercicio.series_texto, '3x10+10')
            self.assertEqual(exercicio.intervalo_segundos, 120)
            self.assertEqual(exercicio.instrucoes, 'Mesma carga e reps em todas as séries')
        self.assertFalse(e['Adução de Quadril na Polia Unilateral'].combinado_com_anterior)

    def test_combinados_cada_um_com_suas_series(self):
        leitura = ler_texto('Supino reto\nA\nSéries: 4x8\n\nCrucifixo\nB\nSéries: 4x12\n\nTríceps corda\nSéries: 3x12')
        supino, crucifixo, triceps = leitura.exercicios
        self.assertEqual((supino.letra, crucifixo.letra, triceps.letra), ('A', 'B', ''))
        self.assertEqual((supino.repeticoes, crucifixo.repeticoes), (8, 12))
        self.assertTrue(crucifixo.combinado_com_anterior)
        self.assertFalse(triceps.combinado_com_anterior)

    def test_sem_linhas_em_branco(self):
        leitura = ler_texto('Leg press\nSéries: 4x12\nCarga: 120kg\nStiff\nSéries: 3x10\nCarga: 30 kg')
        self.assertEqual([e.nome for e in leitura.exercicios], ['Leg press', 'Stiff'])
        self.assertEqual(leitura.exercicios[0].carga_kg, Decimal('120'))

    def test_sem_series_usa_padrao_e_avisa(self):
        leitura = ler_texto('Prancha\nInstruções:\n30 segundos')
        self.assertEqual((leitura.exercicios[0].series, leitura.exercicios[0].repeticoes), (3, 10))
        self.assertEqual(leitura.exercicios[0].instrucoes, '30 segundos')
        self.assertIn('Prancha: sem "Séries"; usei 3x10.', leitura.avisos)

    def test_formatos_de_series_e_intervalo(self):
        self.assertEqual(ler_series('3x10'), (3, 10, False))
        self.assertEqual(ler_series('4 x 8-10'), (4, 8, False))
        self.assertEqual(ler_series('3/10 cada lado'), (3, 10, True))
        self.assertIsNone(ler_series('até a falha'))
        self.assertEqual(ler_intervalo('60s'), 60)
        self.assertEqual(ler_intervalo('2min'), 120)
        self.assertEqual(ler_intervalo('1:30'), 90)
        self.assertIsNone(ler_intervalo('livre'))

    def test_exercicio_por_tempo(self):
        leitura = ler_texto('Prancha\nSéries: 3x30s\n\nPrancha lateral\nSéries: 3\nTempo: 40s cada lado\n\n'
                            'Agachamento\nSéries: 3x12')
        prancha, lateral, agachamento = leitura.exercicios
        self.assertEqual((prancha.series, prancha.tempo_segundos), (3, 30))
        self.assertEqual((lateral.series, lateral.tempo_segundos, lateral.cada_lado), (3, 40, True))
        self.assertIsNone(agachamento.tempo_segundos)
        self.assertEqual(agachamento.repeticoes, 12)
        self.assertEqual(leitura.avisos, [])

    def test_formatos_de_tempo(self):
        self.assertEqual(ler_series_por_tempo('3x30s'), (3, 30, False))
        self.assertEqual(ler_series_por_tempo('2x1min cada lado'), (2, 60, True))
        self.assertEqual(ler_series_por_tempo('4x1:30'), (4, 90, False))
        self.assertIsNone(ler_series_por_tempo('3x10'))

    def test_texto_vazio(self):
        self.assertEqual(ler_texto('  \n\n ').exercicios, [])


class FiltrosTest(TestCase):
    def test_filtros(self):
        self.assertEqual(intervalo(45), '45s')
        self.assertEqual(intervalo(120), '2 min')
        self.assertEqual(intervalo(150), '2min30')
        self.assertEqual(carga(Decimal('12.50')), '12,5 kg')
        self.assertEqual(carga(Decimal('0.00')), '0 kg')
        self.assertEqual(video_embed('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(video_embed('https://youtu.be/dQw4w9WgXcQ?t=3'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(video_embed('https://www.instagram.com/reel/abc/'), '')


class CadastroDeSeriesTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.client.login(username='caio@email.com', password=SENHA)

    def test_previa_nao_salva(self):
        resposta = self.client.post(reverse('treinos_nova'), {
            'nome': 'Inferiores', 'dias': ['seg', 'qui'], 'ativa': 'on', 'modo': 'texto', 'texto': INFERIORES, 'acao': 'previa'})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Entendi 10 exercícios, com 1 grupo de combinados')
        self.assertContains(resposta, 'Salvar série com 10 exercícios')
        self.assertFalse(FichaTreino.objects.exists())

    def test_salvar_cria_a_serie_com_os_exercicios(self):
        resposta = self.client.post(reverse('treinos_nova'), {
            'nome': 'Inferiores', 'dias': ['qui', 'seg'], 'ativa': 'on', 'modo': 'texto', 'texto': INFERIORES, 'acao': 'salvar'})
        ficha = FichaTreino.objects.get()
        self.assertRedirects(resposta, reverse('treinos_ficha', args=[ficha.id]))
        self.assertEqual(ficha.usuario, self.usuario)
        self.assertEqual(ficha.dias_semana, 'seg,qui')
        self.assertTrue(ficha.ativa)
        exercicios = list(ficha.exercicios.order_by('ordem_execucao'))
        self.assertEqual([e.ordem_execucao for e in exercicios], list(range(1, 11)))
        self.assertEqual(exercicios[4].nome_exercicio, 'Agachamento Frontal com Halter')
        self.assertTrue(exercicios[4].combinado_com_anterior)

    def test_pagina_da_serie_mostra_os_combinados(self):
        ficha = servicos.criar_ficha(self.usuario, 'Inferiores', ['seg'], exercicios_lidos=ler_texto(INFERIORES).exercicios)
        resposta = self.client.get(reverse('treinos_ficha', args=[ficha.id]))
        self.assertContains(resposta, 'Exercícios combinados · alterne A e B')
        self.assertContains(resposta, '3x10+10')
        self.assertContains(resposta, '3/10 cada lado')
        self.assertContains(resposta, '2 min')
        self.assertContains(resposta, '15 kg')

    def test_serie_sem_texto_para_ir_exercicio_por_exercicio(self):
        self.client.post(reverse('treinos_nova'), {'nome': 'Superiores', 'ativa': 'on', 'modo': 'texto', 'acao': 'salvar'})
        ficha = FichaTreino.objects.get()
        self.assertFalse(ficha.exercicios.exists())
        resposta = self.client.post(reverse('treinos_novo_exercicio', args=[ficha.id]), {
            'nome_exercicio': 'Supino reto', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '8', 'carga_kg': '40', 'intervalo': '90s'})
        self.assertRedirects(resposta, reverse('treinos_ficha', args=[ficha.id]))
        supino = ficha.exercicios.get()
        self.assertEqual((supino.series_planejadas, supino.repeticoes_planejadas, supino.carga_kg), (4, 8, Decimal('40')))
        self.assertEqual(supino.intervalo_segundos, 90)
        self.assertEqual(supino.ordem_execucao, 1)

    def linhas(self, *exercicios, extra=0):
        """Dados do formulário "um por um": uma linha por exercício (+ linhas em branco)."""
        dados = {'ex-TOTAL_FORMS': str(len(exercicios) + extra), 'ex-INITIAL_FORMS': '0',
                 'ex-MIN_NUM_FORMS': '0', 'ex-MAX_NUM_FORMS': '60'}
        for i, campos in enumerate(exercicios):
            base = {'series': '3', 'medida': 'repeticoes', 'repeticoes': '10'}
            base.update(campos)
            dados.update({'ex-%d-%s' % (i, k): v for k, v in base.items()})
        for i in range(len(exercicios), len(exercicios) + extra):
            dados.update({'ex-%d-series' % i: '3', 'ex-%d-medida' % i: 'repeticoes', 'ex-%d-repeticoes' % i: '10'})
        return dados

    def test_montar_um_por_um(self):
        dados = {'nome': 'Core', 'ativa': 'on', 'modo': 'linhas', 'acao': 'salvar'}
        dados.update(self.linhas(
            {'nome': 'Cadeira extensora', 'series': '4', 'repeticoes': '12', 'carga': '35', 'intervalo': '60'},
            {'nome': 'Prancha', 'medida': 'tempo', 'tempo': '45s', 'intervalo': '30s'},
            {'nome': 'Afundo', 'repeticoes': '10', 'cada_lado': 'on'},
            extra=2,  # linhas em branco são ignoradas
        ))
        resposta = self.client.post(reverse('treinos_nova'), dados)
        ficha = FichaTreino.objects.get()
        self.assertRedirects(resposta, reverse('treinos_ficha', args=[ficha.id]))
        extensora, prancha, afundo = ficha.exercicios.order_by('ordem_execucao')
        self.assertEqual((extensora.series_planejadas, extensora.repeticoes_planejadas, extensora.carga_kg,
                          extensora.intervalo_segundos, extensora.tempo_segundos), (4, 12, Decimal('35'), 60, None))
        self.assertEqual((prancha.series_planejadas, prancha.tempo_segundos, prancha.intervalo_segundos), (3, 45, 30))
        self.assertTrue(afundo.cada_lado)
        pagina = self.client.get(reverse('treinos_ficha', args=[ficha.id]))
        self.assertContains(pagina, '3x45s')
        self.assertContains(pagina, '3x10 cada lado')

    def test_linha_por_tempo_sem_tempo_da_erro(self):
        dados = {'nome': 'Core', 'modo': 'linhas', 'acao': 'salvar'}
        dados.update(self.linhas({'nome': 'Prancha', 'medida': 'tempo', 'tempo': ''}))
        resposta = self.client.post(reverse('treinos_nova'), dados)
        self.assertContains(resposta, 'Informe o tempo de cada série')
        self.assertFalse(FichaTreino.objects.exists())

    def test_tela_nova_tem_os_dois_modos(self):
        resposta = self.client.get(reverse('treinos_nova'))
        self.assertContains(resposta, 'Um por um')
        self.assertContains(resposta, 'Colar o texto')
        self.assertContains(resposta, 'name="ex-0-nome"')
        self.assertContains(resposta, 'id="linha-modelo"')

    def test_exercicio_por_tempo_no_formulario(self):
        ficha = servicos.criar_ficha(self.usuario, 'Core', [])
        self.client.post(reverse('treinos_novo_exercicio', args=[ficha.id]), {
            'nome_exercicio': 'Prancha', 'series': '3', 'medida': 'tempo', 'tempo': '1min', 'carga_kg': '0'})
        prancha = ficha.exercicios.get()
        self.assertEqual(prancha.tempo_segundos, 60)
        self.assertEqual(series_de(prancha), '3x60s')

    def test_editar_numeros_descarta_o_texto_da_ficha(self):
        ficha = servicos.criar_ficha(self.usuario, 'Pernas', [], exercicios_lidos=ler_texto(
            'Agachamento\nSéries: 3x10+10').exercicios)
        agachamento = ficha.exercicios.get()
        base = {'nome_exercicio': 'Agachamento', 'series': '3', 'medida': 'repeticoes', 'repeticoes': '10',
                'carga_kg': '0'}
        self.client.post(reverse('treinos_editar_exercicio', args=[agachamento.id]), {**base, 'carga_kg': '20'})
        agachamento.refresh_from_db()
        self.assertEqual(agachamento.series_texto, '3x10+10')  # só mudou a carga
        self.client.post(reverse('treinos_editar_exercicio', args=[agachamento.id]), {**base, 'repeticoes': '12'})
        agachamento.refresh_from_db()
        self.assertEqual((agachamento.series_texto, agachamento.repeticoes_planejadas), ('', 12))

    def test_texto_sem_exercicio_da_erro(self):
        resposta = self.client.post(reverse('treinos_nova'), {'nome': 'X', 'modo': 'texto', 'texto': 'Séries: 3x10', 'acao': 'salvar'})
        self.assertContains(resposta, 'Não encontrei nenhum exercício no texto.')
        self.assertFalse(FichaTreino.objects.exists())

    def test_colar_mais_exercicios_no_fim(self):
        ficha = servicos.criar_ficha(self.usuario, 'Inferiores', [], exercicios_lidos=ler_texto('Leg press\nSéries: 4x12').exercicios)
        self.client.post(reverse('treinos_colar', args=[ficha.id]), {'texto': 'Stiff\nSéries: 3x10', 'acao': 'salvar'})
        self.assertEqual(list(ficha.exercicios.order_by('ordem_execucao').values_list('nome_exercicio', flat=True)),
                         ['Leg press', 'Stiff'])

    def test_series_invalidas_no_formulario(self):
        ficha = servicos.criar_ficha(self.usuario, 'A', [])
        resposta = self.client.post(reverse('treinos_novo_exercicio', args=[ficha.id]), {
            'nome_exercicio': 'Rosca', 'series': '3', 'medida': 'repeticoes', 'repeticoes': '', 'carga_kg': '0'})
        self.assertContains(resposta, 'Informe as repetições.')
        self.assertFalse(ficha.exercicios.exists())


class AtivaInativaTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.client.login(username='caio@email.com', password=SENHA)
        self.ficha = servicos.criar_ficha(self.usuario, 'Inferiores', ['seg', 'qui'])

    def test_inativar_e_ativar(self):
        self.client.post(reverse('treinos_alternar_ativa', args=[self.ficha.id]))
        self.ficha.refresh_from_db()
        self.assertFalse(self.ficha.ativa)
        self.client.post(reverse('treinos_alternar_ativa', args=[self.ficha.id]))
        self.ficha.refresh_from_db()
        self.assertTrue(self.ficha.ativa)

    def test_lista_separa_ativas_e_inativas_e_monta_a_semana(self):
        servicos.criar_ficha(self.usuario, 'Superiores antigo', ['ter'], ativa=False)
        resposta = self.client.get(reverse('treinos_lista'))
        self.assertEqual([f.nome_ficha for f in resposta.context['ativas']], ['Inferiores'])
        self.assertEqual([f.nome_ficha for f in resposta.context['inativas']], ['Superiores antigo'])
        semana = resposta.context['semana']
        self.assertEqual([f.nome_ficha for f in semana['seg']], ['Inferiores'])
        self.assertEqual(semana['ter'], [])  # inativa não entra na semana

    def test_editar_nome_dias_e_situacao(self):
        self.client.post(reverse('treinos_editar_ficha', args=[self.ficha.id]), {'nome': 'Pernas', 'dias': ['sex']})
        self.ficha.refresh_from_db()
        self.assertEqual((self.ficha.nome_ficha, self.ficha.dias_semana, self.ficha.ativa), ('Pernas', 'sex', False))

    def test_outra_pessoa_nao_ve_nem_mexe(self):
        criar_usuario(email='outra@email.com', cpf='11144477735')
        self.client.login(username='outra@email.com', password=SENHA)
        self.assertEqual(self.client.get(reverse('treinos_ficha', args=[self.ficha.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('treinos_alternar_ativa', args=[self.ficha.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('treinos_excluir_ficha', args=[self.ficha.id])).status_code, 404)
        self.assertTrue(FichaTreino.objects.filter(id=self.ficha.id, ativa=True).exists())

    def test_precisa_de_login(self):
        self.client.logout()
        resposta = self.client.get(reverse('treinos_lista'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse('entrar'), resposta.url)


class OrdemEExclusaoTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.client.login(username='caio@email.com', password=SENHA)
        texto = 'Afundo\nA\n\nAgachamento\nB\nSéries: 3x10\n\nCadeira extensora\nSéries: 3x15'
        self.ficha = servicos.criar_ficha(self.usuario, 'Inferiores', [], exercicios_lidos=ler_texto(texto).exercicios)

    def nomes(self):
        return list(self.ficha.exercicios.order_by('ordem_execucao').values_list('nome_exercicio', flat=True))

    def test_mover_para_cima_e_para_baixo(self):
        extensora = self.ficha.exercicios.get(nome_exercicio='Cadeira extensora')
        self.client.post(reverse('treinos_mover_exercicio', args=[extensora.id]), {'direcao': 'cima'})
        self.assertEqual(self.nomes(), ['Afundo', 'Cadeira extensora', 'Agachamento'])
        self.client.post(reverse('treinos_mover_exercicio', args=[extensora.id]), {'direcao': 'baixo'})
        self.assertEqual(self.nomes(), ['Afundo', 'Agachamento', 'Cadeira extensora'])

    def test_primeiro_nao_sobe(self):
        afundo = self.ficha.exercicios.get(nome_exercicio='Afundo')
        self.assertFalse(servicos.mover(afundo, para_cima=True))

    def test_excluir_o_primeiro_do_grupo_desfaz_a_combinacao(self):
        afundo = self.ficha.exercicios.get(nome_exercicio='Afundo')
        self.client.post(reverse('treinos_excluir_exercicio', args=[afundo.id]))
        agachamento = self.ficha.exercicios.get(nome_exercicio='Agachamento')
        self.assertEqual(agachamento.ordem_execucao, 1)
        self.assertFalse(agachamento.combinado_com_anterior)

    def test_blocos_com_letras(self):
        blocos = servicos.blocos_da_ficha(list(self.ficha.exercicios.order_by('ordem_execucao')))
        self.assertEqual([len(b.exercicios) for b in blocos], [2, 1])
        self.assertEqual([e.letra for e in blocos[0].exercicios], ['A', 'B'])
        self.assertEqual(blocos[1].exercicios[0].letra, '')

    def test_excluir_a_serie(self):
        self.client.post(reverse('treinos_excluir_ficha', args=[self.ficha.id]))
        self.assertFalse(FichaTreino.objects.exists())
        self.assertFalse(ExercicioFicha.objects.exists())


@override_settings(MEDIA_ROOT=MIDIA_DE_TESTE)
class ImagemEVideoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MIDIA_DE_TESTE, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.usuario = criar_usuario()
        self.client.login(username='caio@email.com', password=SENHA)
        self.ficha = servicos.criar_ficha(self.usuario, 'Inferiores', [])

    def criar(self, **extra):
        dados = {'nome_exercicio': 'Leg press', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '12', 'carga_kg': '100', 'imagem': imagem_png(),
                 'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        dados.update(extra)
        self.client.post(reverse('treinos_novo_exercicio', args=[self.ficha.id]), dados)
        return self.ficha.exercicios.get()

    def test_salva_imagem_e_mostra_o_video(self):
        exercicio = self.criar()
        self.assertTrue(exercicio.imagem.name.startswith('exercicios/'))
        self.assertTrue(exercicio.imagem.storage.exists(exercicio.imagem.name))
        resposta = self.client.get(reverse('treinos_ficha', args=[self.ficha.id]))
        self.assertContains(resposta, exercicio.imagem.url)
        self.assertContains(resposta, 'youtube-nocookie.com/embed/dQw4w9WgXcQ')

    def test_arquivo_que_nao_e_imagem_e_recusado(self):
        falso = SimpleUploadedFile('virus.png', b'nao sou imagem', content_type='image/png')
        resposta = self.client.post(reverse('treinos_novo_exercicio', args=[self.ficha.id]), {
            'nome_exercicio': 'Leg press', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '12', 'carga_kg': '0', 'imagem': falso})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(self.ficha.exercicios.exists())

    def test_trocar_imagem_apaga_a_antiga(self):
        exercicio = self.criar()
        antiga = exercicio.imagem.name
        self.client.post(reverse('treinos_editar_exercicio', args=[exercicio.id]), {
            'nome_exercicio': 'Leg press', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '12', 'carga_kg': '100', 'imagem': imagem_png('novo.png')})
        exercicio.refresh_from_db()
        self.assertNotEqual(exercicio.imagem.name, antiga)
        self.assertTrue(exercicio.imagem.storage.exists(exercicio.imagem.name))
        self.assertFalse(exercicio.imagem.storage.exists(antiga))

    def test_remover_imagem(self):
        exercicio = self.criar()
        antiga = exercicio.imagem.name
        self.client.post(reverse('treinos_editar_exercicio', args=[exercicio.id]), {
            'nome_exercicio': 'Leg press', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '12', 'carga_kg': '100', 'remover_imagem': 'on'})
        exercicio.refresh_from_db()
        self.assertFalse(exercicio.imagem)
        self.assertFalse(exercicio.imagem.storage.exists(antiga))

    def test_excluir_exercicio_apaga_a_imagem(self):
        exercicio = self.criar()
        nome = exercicio.imagem.name
        storage = exercicio.imagem.storage
        self.client.post(reverse('treinos_excluir_exercicio', args=[exercicio.id]))
        self.assertFalse(storage.exists(nome))

    def test_editar_sem_mexer_na_imagem_mantem(self):
        exercicio = self.criar()
        nome = exercicio.imagem.name
        self.client.post(reverse('treinos_editar_exercicio', args=[exercicio.id]), {
            'nome_exercicio': 'Leg press 45°', 'series': '4', 'medida': 'repeticoes', 'repeticoes': '10', 'carga_kg': '110', 'intervalo': '2min',
            'video_url': ''})
        exercicio.refresh_from_db()
        self.assertEqual(exercicio.imagem.name, nome)
        self.assertEqual((exercicio.nome_exercicio, exercicio.repeticoes_planejadas, exercicio.intervalo_segundos),
                         ('Leg press 45°', 10, 120))
