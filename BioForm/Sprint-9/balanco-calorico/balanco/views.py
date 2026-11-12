from django.shortcuts import render

from diario import servicos as diario
from diario.views import diario_view

from .servicos import Balanco, MetaComTreinos


@diario_view
def dia(request, usuario, data=None):
    """Balanço do dia: o que comeu, o que gastou (com os treinos feitos) e como a meta foi ajustada."""
    data = data or diario.hoje()
    resumo = diario.resumo_do_dia(usuario, data)  # a meta do diário já vem ajustada pelos treinos
    balanco = Balanco(resumo.meta, resumo.total['kcal']) if isinstance(resumo.meta, MetaComTreinos) else None
    return render(request, 'balanco/dia.html', {
        'usuario': usuario, 'secao': 'diario', 'data': data, 'eh_hoje': data == diario.hoje(),
        'resumo': resumo, 'balanco': balanco,
    })
