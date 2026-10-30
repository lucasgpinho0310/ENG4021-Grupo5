"""
Regras das séries de academia (fichas de treino de musculação): criar a partir do texto colado,
montar os grupos de exercícios combinados, reordenar, ativar/inativar e apagar as imagens junto.
"""
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Max, Q

from saude.models import DIAS_DA_SEMANA, EsporteUsuario, ExercicioFicha, FichaTreino, dias_da_lista

from .leitor import LETRAS


@dataclass
class Bloco:
    """Um exercício sozinho ou um grupo de exercícios combinados (A, B...), na ordem da ficha."""
    exercicios: list

    @property
    def combinado(self):
        return len(self.exercicios) > 1


def blocos_da_ficha(exercicios):
    """Agrupa os exercícios: cada um marcado como "combinado com o anterior" entra no bloco de cima."""
    blocos = []
    for exercicio in exercicios:
        if exercicio.combinado_com_anterior and blocos:
            blocos[-1].exercicios.append(exercicio)
        else:
            blocos.append(Bloco([exercicio]))
    for bloco in blocos:
        for posicao, exercicio in enumerate(bloco.exercicios):
            exercicio.letra = LETRAS[posicao % len(LETRAS)] if bloco.combinado else ''
    return blocos


def fichas_do_usuario(usuario):
    return (
        FichaTreino.objects.filter(usuario=usuario)
        .annotate(total_exercicios=Count('exercicios'))
        .order_by('-ativa', 'nome_ficha')
    )


def musculacao_do_perfil(usuario):
    """O registro de musculação do perfil (vezes por semana, dias fixos), se houver."""
    return (
        EsporteUsuario.objects.filter(usuario=usuario, esporte__nome__iexact='Musculação')
        .select_related('esporte').first()
    )


def semana_das_fichas(fichas):
    """{dia: [fichas ativas daquele dia]} para os 7 dias."""
    semana = {dia: [] for dia in DIAS_DA_SEMANA}
    for ficha in fichas:
        if ficha.ativa:
            for dia in ficha.lista_dias():
                semana[dia].append(ficha)
    return semana


def proxima_ordem(ficha):
    return (ficha.exercicios.aggregate(maior=Max('ordem_execucao'))['maior'] or 0) + 1


def adicionar_lidos(ficha, exercicios_lidos):
    """Grava no fim da ficha os exercícios lidos do texto colado (leitor.ler_texto)."""
    ordem = proxima_ordem(ficha)
    novos = []
    for posicao, lido in enumerate(exercicios_lidos):
        novos.append(ExercicioFicha(
            ficha=ficha,
            nome_exercicio=lido.nome,
            ordem_execucao=ordem + posicao,
            series_planejadas=lido.series,
            repeticoes_planejadas=lido.repeticoes,
            tempo_segundos=lido.tempo_segundos,
            series_texto=lido.series_texto,
            cada_lado=lido.cada_lado,
            carga_kg=lido.carga_kg,
            intervalo_segundos=lido.intervalo_segundos,
            instrucoes=lido.instrucoes,
            # o primeiro exercício colado não se junta ao último que já estava na ficha
            combinado_com_anterior=lido.combinado_com_anterior and posicao > 0,
        ))
    ExercicioFicha.objects.bulk_create(novos)
    return novos


@transaction.atomic
def criar_ficha(usuario, nome, dias, ativa=True, exercicios_lidos=()):
    ficha = FichaTreino.objects.create(
        usuario=usuario,
        nome_ficha=nome,
        dias_semana=','.join(dias_da_lista(','.join(dias))),
        ativa=ativa,
    )
    adicionar_lidos(ficha, exercicios_lidos)
    return ficha


def renumerar(ficha):
    """Deixa a ordem 1, 2, 3... sem buracos (depois de apagar ou mover)."""
    for numero, exercicio in enumerate(ficha.exercicios.order_by('ordem_execucao', 'nome_exercicio'), start=1):
        if exercicio.ordem_execucao != numero:
            exercicio.ordem_execucao = numero
            exercicio.save(update_fields=['ordem_execucao'])


@transaction.atomic
def mover(exercicio, para_cima):
    """Troca o exercício de lugar com o vizinho de cima ou de baixo."""
    ficha = exercicio.ficha
    renumerar(ficha)
    exercicio.refresh_from_db()
    vizinhos = ficha.exercicios.filter(
        Q(ordem_execucao=exercicio.ordem_execucao - 1) if para_cima else Q(ordem_execucao=exercicio.ordem_execucao + 1)
    )
    vizinho = vizinhos.first()
    if vizinho is None:
        return False
    exercicio.ordem_execucao, vizinho.ordem_execucao = vizinho.ordem_execucao, exercicio.ordem_execucao
    exercicio.save(update_fields=['ordem_execucao'])
    vizinho.save(update_fields=['ordem_execucao'])
    return True


def apagar_imagem(exercicio):
    if exercicio.imagem:
        exercicio.imagem.delete(save=False)


@transaction.atomic
def excluir_exercicio(exercicio):
    ficha = exercicio.ficha
    apagar_imagem(exercicio)
    exercicio.delete()
    # quem vinha logo depois e estava combinado com ele passa a se combinar com o de cima, se houver
    renumerar(ficha)
    primeiro = ficha.exercicios.order_by('ordem_execucao').first()
    if primeiro and primeiro.combinado_com_anterior:
        primeiro.combinado_com_anterior = False
        primeiro.save(update_fields=['combinado_com_anterior'])


@transaction.atomic
def excluir_ficha(ficha):
    for exercicio in ficha.exercicios.all():
        apagar_imagem(exercicio)
    ficha.delete()


def alternar_ativa(ficha):
    ficha.ativa = not ficha.ativa
    ficha.save(update_fields=['ativa'])
    return ficha.ativa
