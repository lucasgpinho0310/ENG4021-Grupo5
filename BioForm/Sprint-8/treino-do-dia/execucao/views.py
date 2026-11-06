from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from saude.models import FichaTreino
from treinos.servicos import blocos_da_ficha, musculacao_do_perfil
from treinos.views import treinos_view

from . import servicos
from .forms import TreinoForm


@treinos_view
def fazer(request, usuario, ficha_id):
    """Treino do dia: marca as séries feitas (já vêm preenchidas) e salva o treino no histórico."""
    ficha = get_object_or_404(FichaTreino, id=ficha_id, usuario=usuario)
    exercicios = list(ficha.exercicios.all())
    if not exercicios:
        messages.error(request, 'Adicione exercícios à série antes de começar o treino.')
        return redirect('treinos:treinos_ficha', ficha_id=ficha.id)

    plano = servicos.plano_do_treino(exercicios)
    perfil = musculacao_do_perfil(usuario)
    form = TreinoForm(request.POST or None, initial={
        'data': timezone.localdate(),
        'duracao': perfil.duracao_minutos if perfil and perfil.duracao_minutos else 60,
        'intensidade': perfil.intensidade if perfil else 'moderada',
    })
    erro_series = ''
    if request.method == 'POST':
        marcadas = servicos.ler_series(plano, request.POST)
        tem_erro = any(linha.erro for item in plano for linha in item.linhas)
        if not marcadas:
            erro_series = 'Marque pelo menos uma série feita.'
        if form.is_valid() and marcadas and not tem_erro:
            dados = form.cleaned_data
            sessao = servicos.salvar_treino(usuario, ficha, plano, dados['data'], dados['duracao'], dados['intensidade'])
            messages.success(request, 'Treino salvo no seu histórico.')
            return redirect('historico:sessao', sessao_id=sessao.id)

    return render(request, 'execucao/fazer.html', {
        'usuario': usuario, 'secao': 'treinos', 'ficha': ficha, 'form': form, 'erro_series': erro_series,
        'blocos': _blocos_do_plano(plano, exercicios),
    })


def _blocos_do_plano(plano, exercicios):
    """Os blocos da ficha (exercícios combinados A/B juntos), com o plano de cada exercício."""
    por_exercicio = {item.exercicio.id: item for item in plano}
    return [[por_exercicio[e.id] for e in bloco.exercicios] for bloco in blocos_da_ficha(exercicios)]
