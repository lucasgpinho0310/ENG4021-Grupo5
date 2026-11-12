from django.shortcuts import redirect, render

from contas.onboarding import perfil_obrigatorio, proximo_passo

from . import servicos


@perfil_obrigatorio
def semana(request, usuario):
    """A semana comparando o previsto na rotina com os treinos feitos. ?semana=1 = semana passada."""
    passo = proximo_passo(usuario)
    if passo:
        return redirect(passo)
    try:
        semanas_atras = int(request.GET.get('semana', 0))
    except ValueError:
        semanas_atras = 0
    semanas_atras = min(max(semanas_atras, 0), servicos.SEMANAS_PARA_TRAS)
    return render(request, 'aderencia/semana.html', {
        'usuario': usuario, 'secao': 'rotina',
        'semana': servicos.semana_feita(usuario, semanas_atras=semanas_atras),
        'semanas_atras': semanas_atras,
        'anterior': semanas_atras + 1 if semanas_atras < servicos.SEMANAS_PARA_TRAS else None,
        'seguinte': semanas_atras - 1 if semanas_atras > 0 else None,
    })
