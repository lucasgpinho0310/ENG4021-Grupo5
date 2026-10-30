from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    # Leva o usuário ao próximo passo do perfil ou às metas (a home-page fica em bioform/urls.py)
    path('inicio/', views.inicio, name='inicio'),

    # Endereços antigos de login e senha. O site agora usa as rotas accounts/ (ver bioform/urls.py);
    # estas continuam funcionando para os links que já foram compartilhados.
    path('entrar/', views.EntrarView.as_view(), name='entrar'),
    path('sair/', auth_views.LogoutView.as_view(), name='sair'),
    path('cadastro/', views.cadastro, name='cadastro'),

    # Esqueci minha senha (o e-mail aparece no terminal do runserver, ver EMAIL_BACKEND)
    path('senha/esqueci/', auth_views.PasswordResetView.as_view(
        template_name='contas/senha_esqueci.html',
        email_template_name='contas/email_nova_senha.txt',
        subject_template_name='contas/email_nova_senha_assunto.txt',
        success_url=reverse_lazy('senha_enviada'),
    ), name='senha_esqueci'),
    path('senha/esqueci/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='contas/senha_enviada.html',
    ), name='senha_enviada'),
    path('senha/nova/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='contas/senha_nova.html',
        success_url=reverse_lazy('senha_concluida'),
    ), name='senha_nova'),
    path('senha/nova/pronto/', auth_views.PasswordResetCompleteView.as_view(
        template_name='contas/senha_concluida.html',
    ), name='senha_concluida'),

    # Perfil (onboarding: passos 1 a 3; o passo 4, metas, fica no app metas)
    path('perfil/dados/', views.perfil_dados, name='perfil_dados'),
    path('perfil/objetivo/', views.perfil_objetivo, name='perfil_objetivo'),
    path('perfil/esportes/', views.perfil_esportes, name='perfil_esportes'),
    path('perfil/concluir/', views.perfil_concluir, name='perfil_concluir'),

    # Editar perfil (dados da conta)
    path('conta/', views.conta, name='conta'),
    path('conta/senha/', views.TrocarSenhaView.as_view(), name='trocar_senha'),
    path('conta/excluir/', views.excluir_conta, name='excluir_conta'),

    # Equipe
    path('usuarios/', views.usuarios, name='usuarios'),
]
