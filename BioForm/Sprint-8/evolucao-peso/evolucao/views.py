from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo
from saude.models import HistoricoMedida

from . import servicos
from .forms import PesagemForm


def evolucao_view(view):
    """Exige login e perfil completo (as pesagens começam no passo 2 do perfil)."""
    @wraps(view)
    @perfil_obrigatorio
    def interna(request, usuario, *args, **kwargs):
        passo = proximo_passo(usuario)
        if passo:
            return redirect(passo)
        return view(request, usuario, *args, **kwargs)
    return interna


@evolucao_view
def peso(request, usuario):
    form = PesagemForm(request.POST or None, initial={'data': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        recalculou = servicos.registrar_pesagem(usuario, form.cleaned_data['data'], form.cleaned_data['peso'])
        messages.success(request, 'Pesagem registrada.' + (' Suas metas foram recalculadas.' if recalculou else ''))
        return redirect('evolucao:peso')

    medidas = servicos.pesagens(usuario)
    return render(request, 'evolucao/peso.html', {
        'usuario': usuario, 'secao': 'evolucao', 'form': form,
        'linhas': servicos.linhas_da_tabela(medidas),  # tabela: mais recente primeiro
        'grafico': servicos.grafico(medidas, usuario.peso_meta_kg),
        'resumo': servicos.resumo(usuario, medidas),
    })


@evolucao_view
@require_POST
def excluir(request, usuario, medida_id):
    medida = get_object_or_404(HistoricoMedida, id=medida_id, usuario=usuario)
    if servicos.excluir_pesagem(usuario, medida):
        messages.success(request, 'Pesagem excluída.')
    else:
        messages.error(request, 'Mantenha pelo menos uma pesagem: as metas são calculadas a partir dela.')
    return redirect('evolucao:peso')
