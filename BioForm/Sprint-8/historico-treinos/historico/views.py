from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo
from saude.models import SessaoAtividade

from . import servicos


def historico_view(view):
    """Exige login e perfil completo (o mesmo das séries de academia)."""
    @wraps(view)
    @perfil_obrigatorio
    def interna(request, usuario, *args, **kwargs):
        passo = proximo_passo(usuario)
        if passo:
            return redirect(passo)
        return view(request, usuario, *args, **kwargs)
    return interna


def _sessao(usuario, sessao_id):
    return get_object_or_404(SessaoAtividade.objects.select_related('esporte', 'ficha'), id=sessao_id, usuario=usuario)


@historico_view
def lista(request, usuario):
    return render(request, 'historico/lista.html', {
        'usuario': usuario, 'secao': 'treinos',
        'semanas': servicos.semanas_do_usuario(usuario),
        'semanas_no_historico': servicos.SEMANAS_NO_HISTORICO,
    })


@historico_view
def sessao(request, usuario, sessao_id):
    sessao = _sessao(usuario, sessao_id)
    medida = servicos.peso_na_data(usuario, timezone.localdate(sessao.inicio))
    return render(request, 'historico/sessao.html', {
        'usuario': usuario, 'secao': 'treinos', 'sessao': sessao,
        'treino': servicos.treino_feito(sessao, medida.peso_kg if medida else None),
        'exercicios': servicos.exercicios_da_sessao(sessao),
    })


@historico_view
@require_POST
def excluir(request, usuario, sessao_id):
    _sessao(usuario, sessao_id).delete()  # as séries feitas são apagadas junto
    messages.success(request, 'Treino excluído do histórico.')
    return redirect('historico:lista')
