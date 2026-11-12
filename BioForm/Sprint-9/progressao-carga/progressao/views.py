from django.shortcuts import get_object_or_404, render

from saude.models import ExercicioFicha
from treinos.views import treinos_view

from . import servicos


@treinos_view
def exercicio(request, usuario, exercicio_id):
    """Gráfico e tabela da melhor série de cada treino de um exercício da ficha."""
    exercicio = get_object_or_404(ExercicioFicha.objects.select_related('ficha'), id=exercicio_id, ficha__usuario=usuario)
    return render(request, 'progressao/exercicio.html', {
        'usuario': usuario, 'secao': 'treinos', 'exercicio': exercicio,
        'progressao': servicos.progressao(usuario, exercicio),
    })
