from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo
from saude.models import ExercicioFicha, FichaTreino, SessaoAtividade, dias_da_lista

from . import servicos, sessoes
from .forms import (
    EditarFichaForm,
    ExercicioForm,
    ExerciciosLivresFormSet,
    FichaForm,
    LinhasFormSet,
    RegistrarTreinoForm,
    TextoForm,
    TreinoFeitoForm,
)
from .leitor import ler_texto


def treinos_view(view):
    """Exige login e perfil completo (o mesmo do diário)."""
    @wraps(view)
    @perfil_obrigatorio
    def interna(request, usuario, *args, **kwargs):
        passo = proximo_passo(usuario)
        if passo:
            return redirect(passo)
        return view(request, usuario, *args, **kwargs)
    return interna


def _ficha(usuario, ficha_id):
    return get_object_or_404(FichaTreino, id=ficha_id, usuario=usuario)


def _exercicio(usuario, exercicio_id):
    return get_object_or_404(ExercicioFicha.objects.select_related('ficha'), id=exercicio_id, ficha__usuario=usuario)


def _contexto(usuario, **extra):
    return {'usuario': usuario, 'secao': 'treinos', 'musculacao': servicos.musculacao_do_perfil(usuario), **extra}


@treinos_view
def lista(request, usuario):
    fichas = list(servicos.fichas_do_usuario(usuario))
    return render(request, 'treinos/lista.html', _contexto(
        usuario,
        ativas=[f for f in fichas if f.ativa],
        inativas=[f for f in fichas if not f.ativa],
        semana=servicos.semana_das_fichas(fichas),
    ))


@treinos_view
def nova(request, usuario):
    """Nova série: montar um por um (uma linha por exercício) ou colar o texto da ficha."""
    form = FichaForm(request.POST or None)
    linhas = LinhasFormSet(request.POST or None, prefix='ex')
    modo = request.POST.get('modo', 'linhas')
    leitura = None
    if request.method == 'POST' and form.is_valid():
        dados = form.cleaned_data
        exercicios = None
        if modo == 'texto':
            leitura = ler_texto(dados['texto']) if dados['texto'].strip() else None
            if leitura is not None and not leitura.exercicios:
                form.add_error('texto', 'Não encontrei nenhum exercício no texto.')
            elif request.POST.get('acao') != 'previa' or leitura is None:
                exercicios = leitura.exercicios if leitura else []
        elif linhas.is_valid():
            exercicios = linhas.exercicios()
        if exercicios is not None:
            ficha = servicos.criar_ficha(usuario, dados['nome'], dados['dias'], dados['ativa'], exercicios)
            total = len(exercicios)
            if total:
                messages.success(request, 'Série "%s" criada com %d exercício%s.' % (
                    ficha.nome_ficha, total, '' if total == 1 else 's'))
            else:
                messages.success(request, 'Série "%s" criada. Agora adicione os exercícios.' % ficha.nome_ficha)
            return redirect('treinos:treinos_ficha', ficha_id=ficha.id)
    return render(request, 'treinos/nova.html', _contexto(
        usuario, form=form, linhas=linhas, modo=modo, leitura=leitura,
    ))


@treinos_view
def ficha(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    exercicios = list(ficha.exercicios.order_by('ordem_execucao'))
    ultimas = sessoes.ultimas_series(usuario, exercicios)
    for exercicio in exercicios:
        exercicio.ultima = ultimas.get(exercicio.id)  # (sessão, séries) da última vez, para "Última vez"
    return render(request, 'treinos/ficha.html', _contexto(
        usuario, ficha=ficha, exercicios=exercicios, blocos=servicos.blocos_da_ficha(exercicios),
        ultimo_treino=sessoes.sessoes_do_usuario(usuario).filter(ficha=ficha).first(),
    ))


@treinos_view
def editar_ficha(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    form = EditarFichaForm(request.POST or None, initial={
        'nome': ficha.nome_ficha, 'dias': ficha.lista_dias(), 'ativa': ficha.ativa,
    })
    if request.method == 'POST' and form.is_valid():
        ficha.nome_ficha = form.cleaned_data['nome']
        ficha.dias_semana = ','.join(dias_da_lista(','.join(form.cleaned_data['dias'])))
        ficha.ativa = form.cleaned_data['ativa']
        ficha.save(update_fields=['nome_ficha', 'dias_semana', 'ativa'])
        messages.success(request, 'Série atualizada.')
        return redirect('treinos:treinos_ficha', ficha_id=ficha.id)
    return render(request, 'treinos/editar_ficha.html', _contexto(usuario, ficha=ficha, form=form))


@require_POST
@treinos_view
def alternar_ativa(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    if servicos.alternar_ativa(ficha):
        messages.success(request, 'Série "%s" ativada.' % ficha.nome_ficha)
    else:
        messages.success(request, 'Série "%s" inativada. Ela continua salva e pode ser ativada de novo.' % ficha.nome_ficha)
    if request.POST.get('voltar') == 'lista':
        return redirect('treinos:treinos_lista')
    return redirect('treinos:treinos_ficha', ficha_id=ficha.id)


@require_POST
@treinos_view
def excluir_ficha(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    nome = ficha.nome_ficha
    servicos.excluir_ficha(ficha)
    messages.success(request, 'Série "%s" excluída.' % nome)
    return redirect('treinos:treinos_lista')


@treinos_view
def colar(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    form = TextoForm(request.POST or None)
    leitura = None
    if request.method == 'POST' and form.is_valid():
        leitura = ler_texto(form.cleaned_data['texto'])
        if not leitura.exercicios:
            form.add_error('texto', 'Não encontrei nenhum exercício no texto.')
        elif request.POST.get('acao') != 'previa':
            servicos.adicionar_lidos(ficha, leitura.exercicios)
            total = len(leitura.exercicios)
            messages.success(request, '%d exercício%s adicionado%s.' % (total, '' if total == 1 else 's', '' if total == 1 else 's'))
            return redirect('treinos:treinos_ficha', ficha_id=ficha.id)
    return render(request, 'treinos/colar.html', _contexto(usuario, ficha=ficha, form=form, leitura=leitura))


@treinos_view
def novo_exercicio(request, usuario, ficha_id):
    ficha = _ficha(usuario, ficha_id)
    form = ExercicioForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        exercicio = form.save(commit=False)
        exercicio.ficha = ficha
        exercicio.ordem_execucao = servicos.proxima_ordem(ficha)
        exercicio.save()
        messages.success(request, '"%s" adicionado.' % exercicio.nome_exercicio)
        if request.POST.get('acao') == 'outro':
            return redirect('treinos:treinos_novo_exercicio', ficha_id=ficha.id)
        return redirect('treinos:treinos_ficha', ficha_id=ficha.id)
    return render(request, 'treinos/exercicio.html', _contexto(usuario, ficha=ficha, form=form, exercicio=None))


@treinos_view
def editar_exercicio(request, usuario, exercicio_id):
    exercicio = _exercicio(usuario, exercicio_id)
    form = ExercicioForm(request.POST or None, request.FILES or None, instance=exercicio)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '"%s" atualizado.' % exercicio.nome_exercicio)
        return redirect('treinos:treinos_ficha', ficha_id=exercicio.ficha_id)
    return render(request, 'treinos/exercicio.html', _contexto(
        usuario, ficha=exercicio.ficha, form=form, exercicio=exercicio,
    ))


@require_POST
@treinos_view
def excluir_exercicio(request, usuario, exercicio_id):
    exercicio = _exercicio(usuario, exercicio_id)
    ficha_id, nome = exercicio.ficha_id, exercicio.nome_exercicio
    servicos.excluir_exercicio(exercicio)
    messages.success(request, '"%s" removido da série.' % nome)
    return redirect('treinos:treinos_ficha', ficha_id=ficha_id)


@require_POST
@treinos_view
def mover_exercicio(request, usuario, exercicio_id):
    exercicio = _exercicio(usuario, exercicio_id)
    servicos.mover(exercicio, para_cima=request.POST.get('direcao') == 'cima')
    return redirect('%s#ex-%s' % (reverse('treinos:treinos_ficha', args=[exercicio.ficha_id]), exercicio.id))


# =====================================================================
# Treino feito e histórico (RF06 / RF07)
# =====================================================================

POR_PAGINA = 20


def _sessao(usuario, sessao_id):
    return get_object_or_404(SessaoAtividade.objects.select_related('ficha'), id=sessao_id, usuario=usuario)


@treinos_view
def treinar(request, usuario, ficha_id):
    """Registrar o treino feito: cada série com a carga e as repetições de verdade."""
    ficha = _ficha(usuario, ficha_id)
    exercicios = list(ficha.exercicios.order_by('ordem_execucao'))
    if not exercicios:
        messages.error(request, 'Adicione os exercícios da série antes de registrar um treino.')
        return redirect('treinos:treinos_ficha', ficha_id=ficha.id)

    duracao, intensidade = sessoes.padroes_do_perfil(usuario)
    agora = timezone.localtime().replace(second=0, microsecond=0)
    form = TreinoFeitoForm(
        exercicios, sessoes.ultimas_series(usuario, exercicios), request.POST or None,
        initial={'inicio': agora - timedelta(minutes=duracao), 'duracao': duracao, 'intensidade': intensidade},
    )
    if request.method == 'POST' and form.is_valid():
        dados = form.cleaned_data
        sessao = sessoes.registrar_treino(
            usuario, ficha, dados['inicio'], dados['duracao'], dados['intensidade'], form.feitos,
        )
        series = sum(len(s) for _, s in form.feitos)
        messages.success(request, 'Treino salvo: %d série%s de %d exercício%s.' % (
            series, '' if series == 1 else 's', len(form.feitos), '' if len(form.feitos) == 1 else 's'))
        return redirect('treinos:treinos_sessao', sessao_id=sessao.id)
    return render(request, 'treinos/treinar.html', _contexto(usuario, ficha=ficha, form=form))


@treinos_view
def registrar(request, usuario):
    """Registrar treino livre: qualquer esporte, com ou sem lista de exercícios."""
    esportes = sessoes.esportes_para_escolher(usuario)
    duracao, intensidade = sessoes.padroes_do_perfil(usuario)
    agora = timezone.localtime()
    padrao = next((e for e in esportes if e.nome.lower() == sessoes.ESPORTE.lower()), esportes[0] if esportes else None)
    form = RegistrarTreinoForm(esportes, request.POST or None, initial={
        'esporte': padrao.id if padrao else None, 'data': agora.date(), 'hora': agora.strftime('%H:%M'),
        'duracao': duracao, 'intensidade': intensidade,
    })
    exercicios = ExerciciosLivresFormSet(request.POST or None, prefix='ex')
    if request.method == 'POST':
        form_ok, exercicios_ok = form.is_valid(), exercicios.is_valid()  # os dois, para mostrar todos os erros
        if form_ok and exercicios_ok:
            dados = form.cleaned_data
            sessao = sessoes.registrar_treino_livre(
                usuario, dados['esporte'], dados['inicio'], dados['duracao'], dados['intensidade'],
                nome=dados['nome'], observacoes=dados['observacoes'].strip(), distancia_km=dados['distancia'],
                exercicios=exercicios.exercicios(),
            )
            messages.success(request, 'Treino "%s" salvo.' % sessao.nome)
            return redirect('treinos:treinos_sessao', sessao_id=sessao.id)
    return render(request, 'treinos/registrar.html', _contexto(usuario, form=form, exercicios=exercicios))


@treinos_view
def historico(request, usuario):
    pagina = Paginator(sessoes.sessoes_do_usuario(usuario), POR_PAGINA).get_page(request.GET.get('pagina'))
    return render(request, 'treinos/historico.html', _contexto(usuario, pagina=pagina))


@treinos_view
def sessao(request, usuario, sessao_id):
    sessao = _sessao(usuario, sessao_id)
    feitos = sessoes.exercicios_da_sessao(sessao)
    todas = [serie for _, series in feitos for serie in series]
    return render(request, 'treinos/sessao.html', _contexto(
        usuario, sessao=sessao, feitos=feitos, total_series=len(todas), volume=sessoes.volume(todas),
    ))


@require_POST
@treinos_view
def excluir_sessao(request, usuario, sessao_id):
    sessao = _sessao(usuario, sessao_id)
    sessao.delete()  # as séries vão junto (CASCADE)
    messages.success(request, 'Treino excluído do histórico.')
    return redirect('treinos:treinos_historico')
