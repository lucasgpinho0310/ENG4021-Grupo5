"""
Duração e dias fixos de cada esporte, no passo 3 do perfil (contas.forms.EsportesForm).

Para cada esporte do catálogo entram três campos:
- dur_<slug>   minutos de cada treino, em média (15, 30, 45, 60, 90 ou 120)
- fixos_<slug> se tem dias fixos ("sim" ou "nao")
- dias_<slug>  quais dias são fixos. Pode marcar menos dias do que as vezes por semana:
               quem treina 4x e tem 2 dias fixos fica com 2 treinos livres.
"""
from django import forms

from saude.models import DIAS_DA_SEMANA, DURACOES_TREINO, dias_da_lista

MINUTOS_PADRAO = 60
DURACOES = [(str(m), '%d min' % m) for m in DURACOES_TREINO]
DIAS = [(dia, nome[:3]) for dia, nome in DIAS_DA_SEMANA.items()]
TEM_DIAS_FIXOS = [('nao', 'Não, varia'), ('sim', 'Sim')]


def adicionar_campos(form, slug, atual=None):
    """Acrescenta os campos do esporte ao formulário. atual: EsporteUsuario já salvo, se houver."""
    dias = atual.lista_dias_fixos() if atual else []
    form.fields['dur_' + slug] = forms.ChoiceField(
        choices=DURACOES, required=False,
        initial=str(atual.duracao_minutos) if atual else str(MINUTOS_PADRAO),
    )
    form.fields['fixos_' + slug] = forms.ChoiceField(
        choices=TEM_DIAS_FIXOS, required=False, initial='sim' if dias else 'nao',
    )
    form.fields['dias_' + slug] = forms.MultipleChoiceField(choices=DIAS, required=False, initial=dias)


def validar(dados, slug, nome):
    """Mensagem de erro se os dias fixos não fecham com a frequência; None se está tudo certo."""
    if dados.get('fixos_' + slug) != 'sim':
        return None
    dias = dados.get('dias_' + slug) or []
    vezes = int(dados.get('freq_' + slug) or 0)
    if not dias:
        return 'Marque os dias fixos de %s ou responda "Não, varia".' % nome
    if len(dias) > vezes:
        return '%s: você marcou %d dias fixos, mas treina %d vezes por semana.' % (nome, len(dias), vezes)
    return None


def valores(dados, slug):
    """(minutos por treino, dias fixos no formato 'seg,qua') do esporte."""
    minutos = int(dados.get('dur_' + slug) or MINUTOS_PADRAO)
    dias = ''
    if dados.get('fixos_' + slug) == 'sim':
        dias = ','.join(dias_da_lista(','.join(dados.get('dias_' + slug) or [])))
    return minutos, dias


def contexto(form, slug):
    """Nomes e valores dos campos, para o template montar os chips."""
    return {
        'dur_nome': form['dur_' + slug].html_name,
        'dur_valor': str(form['dur_' + slug].value()),
        'fixos_nome': form['fixos_' + slug].html_name,
        'fixos_valor': form['fixos_' + slug].value(),
        'dias_nome': form['dias_' + slug].html_name,
        'dias_valor': [str(dia) for dia in form['dias_' + slug].value() or []],
    }
