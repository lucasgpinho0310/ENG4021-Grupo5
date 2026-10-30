from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo

from .confirmacao import confirmar_rotina, proxima_confirmacao
from .semana import semana_do_usuario


@perfil_obrigatorio
def semana(request, usuario):
    passo = proximo_passo(usuario)
    if passo:
        return redirect(passo)
    return render(request, 'rotina/semana.html', {
        'usuario': usuario,
        'semana': semana_do_usuario(usuario),
        'proxima_confirmacao': proxima_confirmacao(usuario),
        'secao': 'rotina',
    })


@require_POST
@perfil_obrigatorio
def confirmar(request, usuario):
    confirmar_rotina(usuario)
    messages.success(request, 'Rotina confirmada. Perguntamos de novo daqui a um mês.')
    voltar = request.POST.get('voltar', '')
    if url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}):
        return redirect(voltar)
    return redirect('rotina_semana')
