from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from metas.calculo import metas_do_usuario
from saude.models import HistoricoMedida, MetaNutricional, Usuario

from .forms import cpf_valido

User = get_user_model()
CPF_ANA = '52998224725'  # CPFs de teste com dígitos verificadores válidos
CPF_BRUNO = '11144477735'
SENHA = 'treino-forte-2026'


def criar_usuario(nome, cpf):
    return Usuario.objects.create(
        nome_completo=nome,
        cpf=cpf,
        celular='21999990000',
        data_nascimento=date(2000, 1, 1),
        sexo_biologico='feminino',
        altura_cm=165,
        biotipo='mesomorfo',
    )


def dados_cadastro(**extra):
    dados = {
        'nome_completo': 'Ana Souza', 'cpf': '529.982.247-25', 'celular': '(21) 99999-0000',
        'email': 'Ana@Email.com', 'senha': SENHA, 'confirmar': SENHA, 'aceitou_termos': 'on',
    }
    dados.update(extra)
    return dados


class CadastroELoginTest(TestCase):
    def test_validacao_do_cpf(self):
        self.assertTrue(cpf_valido(CPF_ANA))
        self.assertTrue(cpf_valido(CPF_BRUNO))
        self.assertFalse(cpf_valido('52998224724'))
        self.assertFalse(cpf_valido('11111111111'))

    def test_cadastro_cria_conta_e_perfil_e_entra(self):
        resposta = self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.assertRedirects(resposta, reverse('contas:perfil_dados'))
        conta = User.objects.get(email='ana@email.com')
        self.assertTrue(conta.check_password(SENHA))
        self.assertEqual(conta.usuario.cpf, CPF_ANA)
        self.assertEqual(conta.usuario.celular, '21999990000')
        self.assertTrue(conta.usuario.aceitou_termos)
        self.assertEqual(int(self.client.session['_auth_user_id']), conta.pk)

    def test_cadastro_repete_a_validacao_no_servidor(self):
        casos = {
            'cpf': dados_cadastro(cpf='529.982.247-24'),
            'confirmar': dados_cadastro(confirmar='outra-senha-2026'),
            'senha': dados_cadastro(senha='12345678', confirmar='12345678'),
            'aceitou_termos': dados_cadastro(aceitou_termos=''),
            'celular': dados_cadastro(celular='9999'),
        }
        for campo, dados in casos.items():
            with self.subTest(campo=campo):
                resposta = self.client.post(reverse('contas:cadastro'), dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn(campo, resposta.context['form'].errors)
        self.assertFalse(User.objects.exists())

    def test_cpf_e_email_nao_repetem(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        resposta = self.client.post(reverse('contas:cadastro'), dados_cadastro(email='ANA@email.com', cpf=CPF_BRUNO))
        self.assertIn('email', resposta.context['form'].errors)
        resposta = self.client.post(reverse('contas:cadastro'), dados_cadastro(email='outra@email.com'))
        self.assertIn('cpf', resposta.context['form'].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_entrar_com_email_ou_cpf(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        for identificador in ('ana@email.com', 'ANA@EMAIL.COM', CPF_ANA, '529.982.247-25'):
            with self.subTest(identificador=identificador):
                self.client.post(reverse('logout'))
                resposta = self.client.post(reverse('login'), {'username': identificador, 'password': SENHA})
                self.assertRedirects(resposta, reverse('contas:inicio'), fetch_redirect_response=False)

    def test_senha_errada_nao_entra(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        resposta = self.client.post(reverse('login'), {'username': CPF_ANA, 'password': 'errada-123'})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'E-mail/CPF ou senha incorretos.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_lembrar_de_mim(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        self.client.post(reverse('login'), {'username': CPF_ANA, 'password': SENHA})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.post(reverse('logout'))
        self.client.post(reverse('login'), {'username': CPF_ANA, 'password': SENHA, 'lembrar': 'on'})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_paginas_do_perfil_exigem_login(self):
        for nome in ('contas:perfil_dados', 'metas:perfil_metas', 'contas:conta', 'contas:usuarios'):
            with self.subTest(pagina=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(resposta.url.startswith(reverse('login')))

    def test_esqueci_minha_senha_envia_link(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        resposta = self.client.post(reverse('password_reset'), {'email': 'ana@email.com'})
        self.assertRedirects(resposta, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)

    def test_pagina_404_personalizada(self):
        resposta = self.client.get('/pagina-que-nao-existe/')
        self.assertContains(resposta, 'Página não encontrada', status_code=404)


class HomeERotasDoRoteiroTest(TestCase):
    """Home-page e rotas accounts/ do roteiro da disciplina, sem perder os endereços antigos."""

    def test_home_sem_login_mostra_entrar_e_cadastro(self):
        resposta = self.client.get(reverse('home'))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'home.html')
        self.assertContains(resposta, reverse('login'))
        self.assertContains(resposta, reverse('contas:cadastro'))

    def test_home_com_login_mostra_as_paginas(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        resposta = self.client.get(reverse('home'))
        for nome in ('contas:inicio', 'diario:diario_hoje', 'treinos:treinos_lista', 'rotina:rotina_semana', 'metas:perfil_metas', 'contas:conta', 'logout'):
            with self.subTest(link=nome):
                self.assertContains(resposta, reverse(nome))

    def test_rotas_accounts_usam_as_telas_do_bioform(self):
        self.assertEqual(reverse('login'), '/accounts/login/')
        paginas = [
            ('login', 'registration/login.html', 'contas/entrar.html'),
            ('password_reset', 'registration/password_reset_form.html', 'contas/senha_esqueci.html'),
            ('password_reset_done', 'registration/password_reset_done.html', 'contas/senha_enviada.html'),
            ('password_reset_complete', 'registration/password_reset_complete.html', 'contas/senha_concluida.html'),
        ]
        for nome, template, tela in paginas:
            with self.subTest(pagina=nome):
                resposta = self.client.get(reverse(nome))
                self.assertTemplateUsed(resposta, template)
                self.assertTemplateUsed(resposta, tela)

    def test_trocar_senha_em_accounts_volta_para_editar_perfil(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        resposta = self.client.get(reverse('password_change'))
        self.assertTemplateUsed(resposta, 'contas/trocar_senha.html')
        resposta = self.client.post(reverse('password_change'), {
            'old_password': SENHA, 'new_password1': 'outra-senha-2026', 'new_password2': 'outra-senha-2026',
        })
        self.assertRedirects(resposta, reverse('contas:conta'), fetch_redirect_response=False)

    def test_link_do_email_cria_nova_senha(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        self.client.post(reverse('password_reset'), {'email': 'ana@email.com'})
        self.assertEqual(mail.outbox[0].subject, 'BioForm: crie uma nova senha')
        link = next(linha for linha in mail.outbox[0].body.splitlines() if '/accounts/reset/' in linha)
        resposta = self.client.get(link.split('testserver')[1], follow=True)
        self.assertTemplateUsed(resposta, 'contas/senha_nova.html')
        resposta = self.client.post(resposta.redirect_chain[-1][0], {
            'new_password1': 'outra-senha-2026', 'new_password2': 'outra-senha-2026',
        })
        self.assertRedirects(resposta, reverse('password_reset_complete'))
        self.assertTrue(self.client.login(username=CPF_ANA, password='outra-senha-2026'))

    def test_enderecos_antigos_continuam_funcionando(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post('/sair/')
        self.assertNotIn('_auth_user_id', self.client.session)
        for url in ('/entrar/', '/senha/esqueci/', '/senha/esqueci/enviado/', '/senha/nova/pronto/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post('/entrar/', {'username': CPF_ANA, 'password': SENHA})
        self.assertRedirects(resposta, reverse('contas:inicio'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/conta/senha/').status_code, 200)

    def test_esqueci_minha_senha_pelo_endereco_antigo(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.client.post(reverse('logout'))
        resposta = self.client.post('/senha/esqueci/', {'email': 'ana@email.com'})
        self.assertRedirects(resposta, '/senha/esqueci/enviado/')
        self.assertEqual(len(mail.outbox), 1)


class OnboardingTest(TestCase):
    def setUp(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.usuario = Usuario.objects.get(cpf=CPF_ANA)

    def preencher_dados(self, peso='78.5'):
        return self.client.post(reverse('contas:perfil_dados'), {
            'apelido': 'Aninha', 'data_nascimento': '1998-01-15', 'sexo_biologico': 'feminino',
            'peso_kg': peso, 'altura_cm': '168', 'peso_meta_kg': '',
        })

    def onboarding_completo(self):
        self.preencher_dados()
        self.client.post(reverse('contas:perfil_objetivo'), {'biotipo': 'mesomorfo', 'objetivo': 'emagrecimento'})
        return self.client.post(reverse('contas:perfil_esportes'), {
            'pratica_musculacao': 'on', 'freq_musculacao': '5', 'int_musculacao': 'intensa',
            'pratica_corrida': 'on', 'freq_corrida': '2', 'int_corrida': 'moderada',
            'freq_ciclismo': '3', 'int_ciclismo': 'moderada',  # não marcado: deve ser ignorado
        })

    def test_nao_pula_passos(self):
        self.assertRedirects(self.client.get(reverse('contas:perfil_esportes')), reverse('contas:perfil_dados'))
        self.assertRedirects(self.client.get(reverse('metas:perfil_metas')), reverse('contas:perfil_dados'))
        self.preencher_dados()
        self.assertRedirects(self.client.get(reverse('metas:perfil_metas')), reverse('contas:perfil_objetivo'))

    def test_passo_a_passo_ate_as_metas(self):
        self.assertRedirects(self.preencher_dados(), reverse('contas:perfil_objetivo'))
        self.assertFalse(HistoricoMedida.objects.exists())  # o peso espera o objetivo do passo 2
        resposta = self.client.post(reverse('contas:perfil_objetivo'), {'biotipo': 'mesomorfo', 'objetivo': 'emagrecimento'})
        self.assertRedirects(resposta, reverse('contas:perfil_esportes'))
        self.assertRedirects(self.onboarding_completo(), reverse('metas:perfil_metas'))

        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.apelido, 'Aninha')
        self.assertEqual(self.usuario.biotipo, 'mesomorfo')
        medida = self.usuario.medida_atual()
        self.assertEqual(medida.peso_kg, Decimal('78.5'))
        self.assertEqual(medida.objetivo_momento, 'emagrecimento')
        self.assertEqual(sorted(e.esporte.nome for e in self.usuario.esportes.all()), ['Corrida', 'Musculação'])

        metas = metas_do_usuario(self.usuario)
        meta = self.usuario.meta_atual()
        self.assertEqual(meta.meta_calorias, metas.calorias)
        self.assertEqual(meta.meta_proteina_g, Decimal(metas.proteina_g))

        pagina = self.client.get(reverse('metas:perfil_metas'))
        self.assertContains(pagina, 'Suas metas estão prontas!')
        self.assertContains(pagina, 'Passo <b>4</b> de 4')
        self.assertEqual(pagina.context['metas'], metas)

    def test_esporte_marcado_sem_intensidade_da_erro(self):
        self.preencher_dados()
        self.client.post(reverse('contas:perfil_objetivo'), {'biotipo': 'mesomorfo', 'objetivo': 'saude'})
        resposta = self.client.post(reverse('contas:perfil_esportes'), {'pratica_natacao': 'on', 'freq_natacao': '2'})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Escolha a frequência e a intensidade de Natação.')

    def test_editar_peso_depois_recalcula_a_meta(self):
        self.onboarding_completo()
        self.client.get(reverse('contas:perfil_concluir'))
        antes = self.usuario.meta_atual().meta_calorias
        resposta = self.preencher_dados(peso='85')
        self.assertRedirects(resposta, reverse('metas:perfil_metas'))
        self.assertGreater(self.usuario.meta_atual().meta_calorias, antes)
        self.assertEqual(MetaNutricional.objects.filter(usuario=self.usuario).count(), 1)
        self.assertEqual(HistoricoMedida.objects.filter(usuario=self.usuario).count(), 1)  # mesmo dia: corrige
        self.assertEqual(self.usuario.medida_atual().peso_kg, Decimal('85'))

    def test_novo_peso_em_outro_dia_vira_novo_ponto_do_grafico(self):
        self.onboarding_completo()
        self.client.get(reverse('contas:perfil_concluir'))
        HistoricoMedida.objects.update(data_registro=timezone.now() - timedelta(days=7))
        self.preencher_dados(peso='77')
        self.assertEqual(
            list(HistoricoMedida.objects.filter(usuario=self.usuario).values_list('peso_kg', flat=True)),
            [Decimal('77'), Decimal('78.5')],
        )


class ContaEUsuariosTest(TestCase):
    def setUp(self):
        self.client.post(reverse('contas:cadastro'), dados_cadastro())
        self.conta = User.objects.get(email='ana@email.com')

    def test_editar_dados_da_conta(self):
        resposta = self.client.post(reverse('contas:conta'), {
            'nome_completo': 'Ana Souza Lima', 'apelido': 'Aninha', 'email': 'nova@email.com', 'celular': '21988887777',
        })
        self.assertRedirects(resposta, reverse('contas:conta'))
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.email, 'nova@email.com')
        self.assertEqual(self.conta.usuario.nome_completo, 'Ana Souza Lima')
        self.client.post(reverse('logout'))
        resposta = self.client.post(reverse('login'), {'username': 'nova@email.com', 'password': SENHA})
        self.assertEqual(resposta.status_code, 302)

    def test_email_de_outra_conta_nao_pode(self):
        User.objects.create_user(username='bruno@email.com', email='bruno@email.com', password=SENHA)
        resposta = self.client.post(reverse('contas:conta'), {
            'nome_completo': 'Ana Souza', 'apelido': '', 'email': 'Bruno@email.com', 'celular': '21999990000',
        })
        self.assertIn('email', resposta.context['form'].errors)

    def test_excluir_conta_pede_a_senha(self):
        resposta = self.client.post(reverse('contas:excluir_conta'), {'senha': 'errada'})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.conta.pk).exists())
        resposta = self.client.post(reverse('contas:excluir_conta'), {'senha': SENHA})
        self.assertRedirects(resposta, reverse('login'))
        self.assertFalse(User.objects.filter(pk=self.conta.pk).exists())
        self.assertFalse(Usuario.objects.filter(cpf=CPF_ANA).exists())

    def test_listagem_de_usuarios_so_para_a_equipe(self):
        resposta = self.client.get(reverse('contas:usuarios'))
        self.assertEqual(resposta.status_code, 302)

        self.conta.is_staff = True
        self.conta.save()
        criar_usuario('Bruno Lima', CPF_BRUNO)
        resposta = self.client.get(reverse('contas:usuarios'))
        self.assertContains(resposta, 'Ana Souza')
        self.assertContains(resposta, 'Bruno Lima')
        self.assertContains(resposta, '529.***.***-25')  # CPF mascarado

        resposta = self.client.get(reverse('contas:usuarios'), {'q': '111.444'})
        self.assertEqual([u.nome_completo for u in resposta.context['pagina']], ['Bruno Lima'])
        resposta = self.client.get(reverse('contas:usuarios'), {'status': 'completo'})
        self.assertEqual(len(resposta.context['pagina']), 0)

    def test_sair(self):
        resposta = self.client.post(reverse('logout'))
        self.assertRedirects(resposta, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)
