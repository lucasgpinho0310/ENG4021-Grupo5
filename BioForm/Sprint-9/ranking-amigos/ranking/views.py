from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo

from . import servicos
from .forms import AdicionarAmigoForm


def ranking_view(view):
    """Exige login e perfil completo, como as outras telas do BioForm."""
    @wraps(view)
    @perfil_obrigatorio
    def interna(request, usuario, *args, **kwargs):
        passo = proximo_passo(usuario)
        if passo:
            return redirect(passo)
        return view(request, usuario, *args, **kwargs)
    return interna


@ranking_view
def ranking(request, usuario):
    """Ranking da semana entre você e seus amigos. ?semana=1 = semana passada."""
    try:
        semanas_atras = int(request.GET.get('semana', 0))
    except ValueError:
        semanas_atras = 0
    semanas_atras = min(max(semanas_atras, 0), servicos.SEMANAS_PARA_TRAS)
    return render(request, 'ranking/semana.html', {
        'usuario': usuario, 'secao': 'ranking',
        'ranking': servicos.ranking_semanal(usuario, semanas_atras=semanas_atras),
        'semanas_atras': semanas_atras,
        'anterior': semanas_atras + 1 if semanas_atras < servicos.SEMANAS_PARA_TRAS else None,
        'seguinte': semanas_atras - 1 if semanas_atras > 0 else None,
    })


@ranking_view
def amigos(request, usuario):
    """Lista de amigos e o formulário para adicionar um amigo pelo e-mail."""
    form = AdicionarAmigoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            amigo = servicos.adicionar_amigo(usuario, form.cleaned_data['email'])
        except servicos.AmigoInvalido as erro:
            form.add_error('email', str(erro))
        else:
            messages.success(request, '%s agora está no seu ranking.' % amigo)
            return redirect('ranking:amigos')
    return render(request, 'ranking/amigos.html', {
        'usuario': usuario, 'secao': 'ranking', 'form': form,
        'amigos': servicos.amigos_de(usuario),
    })


@ranking_view
@require_POST
def remover(request, usuario, amigo_id):
    if servicos.remover_amigo(usuario, amigo_id):
        messages.success(request, 'Amizade desfeita.')
    return redirect('ranking:amigos')
