from django.apps import apps
from django.shortcuts import render

from contas.onboarding import proximo_passo
from saude.models import Usuario


def home(request):
    '''
    Home-page do BioForm.
    Quem já entrou e completou o perfil vê o painel do dia (app painel, Sprint 10).
    Os outros veem o template home.html, com links para entrar/criar conta
    ou para as páginas do site.
    '''
    if request.user.is_authenticated and apps.is_installed('painel'):
        usuario = Usuario.objects.filter(conta=request.user).first()
        if usuario is not None and proximo_passo(usuario) is None:
            from painel.views import hoje
            return hoje(request)
    return render(request, 'home.html')
