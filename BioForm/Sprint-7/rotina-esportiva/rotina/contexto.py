"""
Context processor (bioform/settings.py): coloca em todas as páginas o aviso de confirmar a rotina,
quando já faz um mês da última confirmação.
"""
from contas.onboarding import SESSAO_ONBOARDING, proximo_passo
from saude.models import Usuario

from .confirmacao import precisa_confirmar

# Páginas onde o aviso não aparece: o próprio passo 3 e a confirmação
PAGINAS_SEM_AVISO = {'perfil_esportes', 'rotina_confirmar'}


def confirmacao_da_rotina(request):
    if not request.user.is_authenticated or request.session.get(SESSAO_ONBOARDING):
        return {}
    pagina = getattr(request.resolver_match, 'url_name', None)
    if pagina in PAGINAS_SEM_AVISO:
        return {}
    usuario = Usuario.objects.filter(conta=request.user).first()
    if usuario is None or proximo_passo(usuario) or not precisa_confirmar(usuario):
        return {}
    return {'rotina_a_confirmar': list(usuario.esportes.select_related('esporte'))}
