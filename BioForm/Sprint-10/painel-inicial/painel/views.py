from django.shortcuts import redirect, render

from contas.onboarding import perfil_obrigatorio, proximo_passo

from . import servicos


@perfil_obrigatorio
def hoje(request, usuario):
    """Painel do dia: alimentação, treino, semana, peso e ranking numa tela só. Também é a home de quem entrou."""
    passo = proximo_passo(usuario)
    if passo:
        return redirect(passo)
    return render(request, 'painel/painel.html', {
        'usuario': usuario, 'secao': 'painel',
        'painel': servicos.painel_do_dia(usuario),
    })
