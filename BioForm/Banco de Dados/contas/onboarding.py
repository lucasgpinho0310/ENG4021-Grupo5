"""Em que passo do onboarding o usuário está (usado pelas telas de perfil e pela tela de metas)."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from saude.models import Usuario

# Chaves guardadas na sessão durante o onboarding
SESSAO_ONBOARDING = 'onboarding'
SESSAO_PESO = 'peso_onboarding'


def proximo_passo(usuario):
    """Nome da URL do primeiro passo do perfil que falta preencher, ou None se está completo."""
    if not (usuario.apelido and usuario.data_nascimento and usuario.sexo_biologico and usuario.altura_cm):
        return 'contas:perfil_dados'
    if not usuario.biotipo or usuario.medida_atual() is None:
        return 'contas:perfil_objetivo'
    if usuario.meta_atual() is None:
        return 'contas:perfil_esportes'
    return None


def em_onboarding(request, usuario):
    return bool(request.session.get(SESSAO_ONBOARDING)) or proximo_passo(usuario) is not None


def perfil_obrigatorio(view):
    """Exige login e uma conta com perfil BioForm. Entrega o perfil como 2º argumento da view."""
    @wraps(view)
    @login_required
    def envoltorio(request, *args, **kwargs):
        usuario = Usuario.objects.filter(conta=request.user).first()
        if usuario is None:
            if request.user.is_staff:  # ex.: superusuário criado pelo createsuperuser
                return redirect('contas:usuarios')
            logout(request)
            messages.error(request, 'Esta conta não tem perfil no BioForm. Crie uma conta para continuar.')
            return redirect('contas:cadastro')
        return view(request, usuario, *args, **kwargs)
    return envoltorio
