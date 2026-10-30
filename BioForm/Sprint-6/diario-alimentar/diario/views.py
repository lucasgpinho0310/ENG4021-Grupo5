from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from contas.onboarding import perfil_obrigatorio, proximo_passo
from saude.models import Alimento, RegistroRefeicao

from . import servicos
from .forms import ComboForm, ItemForm

DIAS_NO_HISTORICO = 14


def diario_view(view):
    """Exige login, perfil completo (precisa da meta) e bloqueia dias futuros."""
    @wraps(view)
    @perfil_obrigatorio
    def envoltorio(request, usuario, *args, **kwargs):
        passo = proximo_passo(usuario)
        if passo:
            messages.error(request, 'Complete seu perfil para usar o diário: ele compara o que você come com a sua meta.')
            return redirect(passo)
        data = kwargs.get('data')
        if data is not None and data > servicos.hoje():
            messages.error(request, 'Não dá para registrar dias futuros.')
            return redirect('diario:diario_hoje')
        return view(request, usuario, *args, **kwargs)
    return envoltorio


def voltar_para(data):
    if data == servicos.hoje():
        return redirect('diario:diario_hoje')
    return redirect('diario:diario_dia', data=data)


@diario_view
def dia(request, usuario, data=None):
    data = data or servicos.hoje()
    resumo = servicos.resumo_do_dia(usuario, data)
    return render(request, 'diario/dia.html', {
        'usuario': usuario,
        'secao': 'diario',
        'resumo': resumo,
        'data': data,
        'eh_hoje': data == servicos.hoje(),
        'anterior': data - timedelta(days=1),
        'proximo': data + timedelta(days=1),
        'minimo': 100 - int(servicos.TOLERANCIA * 100),
        'maximo': 100 + int(servicos.TOLERANCIA * 100),
    })


@diario_view
def adicionar(request, usuario, data):
    tipo = request.GET.get('refeicao') or request.POST.get('tipo_refeicao') or servicos.refeicao_sugerida()
    if tipo not in servicos.NOMES_REFEICAO:
        tipo = servicos.refeicao_sugerida()
    busca = request.GET.get('q', '').strip()

    alimento = None
    form = None
    id_alimento = request.GET.get('alimento') or request.POST.get('alimento')
    if id_alimento:
        try:
            alimento = Alimento.objects.prefetch_related('medidas').get(id=id_alimento)
        except (ObjectDoesNotExist, ValidationError, ValueError):
            raise Http404('Alimento não encontrado.')
        form = ItemForm(alimento, request.POST or None, initial={'tipo_refeicao': tipo})
        if request.method == 'POST' and form.is_valid():
            item = servicos.registrar_item(
                usuario, data, form.cleaned_data['tipo_refeicao'], alimento,
                form.cleaned_data['quantidade_final'], form.cleaned_data['medida_caseira'],
            )
            messages.success(request, '%s: %s (%d kcal).' % (
                servicos.NOMES_REFEICAO[form.cleaned_data['tipo_refeicao']], alimento.nome, round(item.macros()['kcal']),
            ))
            return voltar_para(data)

    return render(request, 'diario/adicionar.html', {
        'usuario': usuario,
        'secao': 'diario',
        'data': data,
        'eh_hoje': data == servicos.hoje(),
        'tipo': tipo,
        'tipos': servicos.TIPOS_REFEICAO,
        'busca': busca,
        'resultados': servicos.buscar_alimentos(busca) if busca else [],
        'recentes': [] if busca else servicos.alimentos_recentes(usuario),
        'combos': servicos.combos_do_usuario(usuario),
        'alimento': alimento,
        'form': form,
    })


@require_POST
@diario_view
def remover_item(request, usuario, item_id):
    try:
        diario = servicos.remover_item(usuario, item_id)
    except (ObjectDoesNotExist, ValidationError):
        raise Http404('Item não encontrado.')
    messages.success(request, 'Alimento removido.')
    return voltar_para(diario.data_referencia)


@require_POST
@diario_view
def agua(request, usuario, data):
    try:
        ml = int(request.POST.get('ml', '0'))
    except ValueError:
        ml = 0
    if ml not in (-250, 250, 500):
        messages.error(request, 'Quantidade de água inválida.')
        return voltar_para(data)
    diario = servicos.adicionar_agua(usuario, data, ml)
    meta = servicos.meta_do_dia(usuario, data)
    if ml > 0 and meta and diario.total_agua_consumida_ml >= meta.meta_agua_ml > diario.total_agua_consumida_ml - ml:
        messages.success(request, 'Meta de água atingida! 💧')
    return voltar_para(data)


@require_POST
@diario_view
def checkin(request, usuario, data):
    if request.POST.get('acao') == 'desfazer':
        servicos.desfazer_dieta(usuario, data)
        messages.success(request, 'Check-in de dieta desfeito.')
    elif servicos.confirmar_dieta(usuario, data):
        messages.success(request, 'Dieta perfeita confirmada! 🔥')
    else:
        messages.error(request, 'Ainda não dá: o dia precisa estar entre %d%% e %d%% da meta de calorias e de cada macro.' % (
            100 - int(servicos.TOLERANCIA * 100), 100 + int(servicos.TOLERANCIA * 100)))
    return voltar_para(data)


@require_POST
@diario_view
def salvar_combo(request, usuario, registro_id):
    form = ComboForm(request.POST)
    registro = get_object_or_404(RegistroRefeicao, id=registro_id, diario__usuario=usuario)
    if form.is_valid():
        servicos.salvar_combo(usuario, registro.id, form.cleaned_data['nome'])
        messages.success(request, 'Combo "%s" salvo. Use em "Adicionar" para lançar tudo de uma vez.' % form.cleaned_data['nome'])
    else:
        messages.error(request, 'Dê um nome ao combo (pelo menos 2 letras).')
    return voltar_para(registro.diario.data_referencia)


@require_POST
@diario_view
def usar_combo(request, usuario, data):
    tipo = request.POST.get('tipo_refeicao')
    if tipo not in servicos.NOMES_REFEICAO:
        tipo = servicos.refeicao_sugerida()
    try:
        combo = servicos.usar_combo(usuario, data, tipo, request.POST.get('combo'))
    except (ObjectDoesNotExist, ValidationError, ValueError):
        raise Http404('Combo não encontrado.')
    messages.success(request, 'Combo "%s" lançado em %s.' % (combo.nome_refeicao, servicos.NOMES_REFEICAO[tipo].lower()))
    return voltar_para(data)


@require_POST
@diario_view
def excluir_combo(request, usuario, combo_id):
    servicos.excluir_combo(usuario, combo_id)
    messages.success(request, 'Combo excluído.')
    voltar = request.POST.get('voltar', '')
    if url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}):
        return redirect(voltar)
    return redirect('diario:diario_hoje')


@diario_view
def historico(request, usuario):
    return render(request, 'diario/historico.html', {
        'usuario': usuario,
        'secao': 'diario',
        'dias': servicos.historico(usuario, DIAS_NO_HISTORICO),
    })
