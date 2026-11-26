"""
Ranking entre amigos: quem são os amigos de cada pessoa e a classificação da semana por XP.

O XP vem do histórico (RegistroXP). Antes de montar o ranking, os treinos e as refeições
registrados na semana viram XP, com os pontos do Documento de Regras de Negócio:
1º treino do dia = 50, outros treinos do mesmo dia = 20 e cada refeição registrada = 10.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from saude.models import (
    PONTOS_POR_ACAO,
    Amizade,
    PerfilGamificacao,
    RegistroRefeicao,
    RegistroXP,
    SessaoAtividade,
    Usuario,
)

SEMANAS_PARA_TRAS = 11  # a semana atual + 11, como no histórico de treinos


class AmigoInvalido(Exception):
    """Não deu para adicionar o amigo; a mensagem explica o motivo para a pessoa."""


# ---------------------------------------------------------------- amigos
def amigos_de(usuario):
    """Os amigos da pessoa. A amizade vale para os dois lados, não importa quem adicionou."""
    return Usuario.objects.filter(
        Q(amizades_enviadas__usuario_2=usuario) | Q(amizades_recebidas__usuario_1=usuario)
    ).distinct()


def adicionar_amigo(usuario, email):
    """Cria a amizade com a pessoa que usa esse e-mail no login. Devolve o novo amigo."""
    amigo = Usuario.objects.filter(conta__email__iexact=email.strip()).first()
    if amigo is None:
        raise AmigoInvalido('Não encontramos ninguém com esse e-mail no BioForm.')
    if amigo == usuario:
        raise AmigoInvalido('Esse é o seu próprio e-mail.')
    if amigos_de(usuario).filter(id=amigo.id).exists():
        raise AmigoInvalido('%s já está na sua lista de amigos.' % amigo)
    Amizade.objects.create(usuario_1=usuario, usuario_2=amigo)
    return amigo


def remover_amigo(usuario, amigo_id):
    """Desfaz a amizade (nos dois sentidos). Devolve True se havia amizade."""
    apagadas, _ = Amizade.objects.filter(
        Q(usuario_1=usuario, usuario_2_id=amigo_id) | Q(usuario_1_id=amigo_id, usuario_2=usuario)
    ).delete()
    return apagadas > 0


# ------------------------------------------------------------------- XP
def limites_da_semana(dia):
    """Segunda e domingo da semana que contém `dia`."""
    segunda = dia - timedelta(days=dia.weekday())
    return segunda, segunda + timedelta(days=6)


def xp_esperado(usuario, segunda, domingo):
    """Quantos registros de XP cada dia da semana deveria ter: {(dia, ação): quantidade}."""
    esperado = Counter()
    sessoes = SessaoAtividade.objects.filter(
        usuario=usuario,
        inicio__date__range=(segunda, domingo),
    )
    treinos_por_dia = Counter(timezone.localtime(s.inicio).date() for s in sessoes)
    for dia, quantidade in treinos_por_dia.items():
        esperado[(dia, 'treino')] = 1
        if quantidade > 1:
            esperado[(dia, 'atividade_secundaria')] = quantidade - 1
    refeicoes = RegistroRefeicao.objects.filter(
        diario__usuario=usuario,
        diario__data_referencia__range=(segunda, domingo),
    ).values_list('diario__data_referencia', flat=True)
    for dia in refeicoes:
        esperado[(dia, 'checkin_refeicao')] += 1
    return esperado


@transaction.atomic
def sincronizar_xp(usuario, segunda, domingo):
    """
    Cria os registros de XP que faltam para os treinos e refeições da semana.
    Pode rodar várias vezes: só cria a diferença entre o esperado e o que já existe.
    Devolve os pontos novos.
    """
    existentes = Counter(
        RegistroXP.objects.filter(usuario=usuario, data_referencia__range=(segunda, domingo))
        .values_list('data_referencia', 'acao')
    )
    novos = []
    for (dia, acao), quantidade in xp_esperado(usuario, segunda, domingo).items():
        for _ in range(quantidade - existentes[(dia, acao)]):
            novos.append(RegistroXP(usuario=usuario, acao=acao, pontos=PONTOS_POR_ACAO[acao], data_referencia=dia))
    if not novos:
        return 0
    RegistroXP.objects.bulk_create(novos)
    pontos = sum(r.pontos for r in novos)
    perfil, _ = PerfilGamificacao.objects.get_or_create(usuario=usuario)
    PerfilGamificacao.objects.filter(id=perfil.id).update(pontos_experiencia=F('pontos_experiencia') + pontos)
    return pontos


# -------------------------------------------------------------- ranking
@dataclass
class Linha:
    """Uma pessoa no ranking da semana."""
    posicao: int
    usuario: object
    xp: int
    treinos: int
    voce: bool
    percentual: int  # tamanho da barra: XP em relação ao líder
    nivel: dict


@dataclass
class Ranking:
    inicio: object
    fim: object
    linhas: list
    voce: Linha
    falta_para_o_proximo: int  # XP para alcançar quem está logo acima (0 se você lidera)
    tem_amigos: bool


def ranking_semanal(usuario, semanas_atras=0, hoje=None):
    """Você e os seus amigos ordenados pelo XP da semana (segunda a domingo)."""
    hoje = hoje or timezone.localdate()
    segunda, domingo = limites_da_semana(hoje - timedelta(weeks=semanas_atras))
    participantes = Usuario.objects.filter(Q(id=usuario.id) | Q(id__in=amigos_de(usuario).values('id')))
    for pessoa in participantes:
        sincronizar_xp(pessoa, segunda, domingo)

    na_semana = Q(registros_xp__data_referencia__range=(segunda, domingo))
    classificacao = (
        participantes
        .annotate(xp_semana=Coalesce(Sum('registros_xp__pontos', filter=na_semana), 0))
        .select_related('perfilgamificacao')
        .order_by('-xp_semana', 'nome_completo')
    )
    treinos = dict(
        SessaoAtividade.objects.filter(usuario__in=participantes, inicio__date__range=(segunda, domingo))
        .order_by().values_list('usuario').annotate(total=Count('id'))
    )
    maior_xp = max((p.xp_semana for p in classificacao), default=0)
    linhas = []
    for indice, pessoa in enumerate(classificacao, start=1):
        empatou = linhas and linhas[-1].xp == pessoa.xp_semana
        perfil = getattr(pessoa, 'perfilgamificacao', None) or PerfilGamificacao(usuario=pessoa)
        linhas.append(Linha(
            posicao=linhas[-1].posicao if empatou else indice,
            usuario=pessoa,
            xp=pessoa.xp_semana,
            treinos=treinos.get(pessoa.id, 0),
            voce=pessoa.id == usuario.id,
            percentual=round(100 * pessoa.xp_semana / maior_xp) if maior_xp else 0,
            nivel=perfil.nivel(),
        ))
    voce = next(linha for linha in linhas if linha.voce)
    acima = [linha.xp for linha in linhas if linha.xp > voce.xp]
    return Ranking(
        inicio=segunda, fim=domingo, linhas=linhas, voce=voce,
        falta_para_o_proximo=min(acima) - voce.xp if acima else 0,
        tem_amigos=len(linhas) > 1,
    )
