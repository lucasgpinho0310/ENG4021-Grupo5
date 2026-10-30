"""
Lê uma série de academia colada como texto e separa os exercícios.

Formato esperado (o mesmo dos apps de treino e das fichas do personal), um exercício por bloco:

    Cadeira Extensora
    Séries: 3x15
    Carga: 0kg
    Intervalo: 60s
    Instruções:
    Última série até não conseguir mais

- A primeira linha do bloco é o nome do exercício.
- "Séries" aceita 3x15, 3/15, 3 x 15, "3/10 cada lado", "3x10+10"... Exercício por tempo (prancha,
  isometria): "3x30s", "3x1min", ou "Séries: 3" com "Tempo: 40s".
- "Carga" em kg, "Intervalo" em segundos (60s) ou minutos (2min, 1:30). As instruções vão até o fim do bloco.
- Exercícios combinados: cada nome seguido de uma letra (A, B...). As séries, a carga e o intervalo
  escritos uma vez valem para todos os exercícios do grupo.
- Linhas em branco separam os blocos, mas não são obrigatórias: toda linha que não é campo
  ("Séries", "Carga"...), letra ou instrução começa um exercício novo.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

SERIES_PADRAO = 3
REPETICOES_PADRAO = 10
LIMITE_EXERCICIOS = 60
LETRAS = 'ABCDEFGH'


def sem_acento(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()


CAMPO = re.compile(r'^\s*(series?|repeticoes|reps|tempo|duracao|carga|peso|intervalo|descanso|instrucoes|obs|observacoes)\s*:\s*(.*)$')
SERIES = re.compile(r'(\d+)\s*(?:x|/|×|series? de)\s*(\d+)')
SERIES_TEMPO = re.compile(r'(\d+)\s*(?:x|/|×|series? de)\s*(\d+(?::\d{2}|(?:[.,]\d+)?\s*(?:s\b|seg|segundos?|min|minutos?|")))')
SO_NUMERO = re.compile(r'^\s*(\d+)\s*(?:series?)?\s*$')
NUMERO = re.compile(r'\d+(?:[.,]\d+)?')
LETRA = re.compile(r'^[A-H]$')
ABRE_GRUPO = ('exercicios combinados', 'exercicio combinado', 'bi-set', 'biset', 'tri-set', 'triset', 'superserie')
IGNORAR = ('alterne esses exercicios', 'alterne os exercicios', 'alterne entre')


@dataclass
class ExercicioLido:
    nome: str
    series: int = SERIES_PADRAO
    repeticoes: int = REPETICOES_PADRAO
    series_texto: str = ''
    cada_lado: bool = False
    carga_kg: Decimal = Decimal('0')
    intervalo_segundos: int | None = None
    tempo_segundos: int | None = None  # exercício por tempo: segundos de cada série
    instrucoes: str = ''
    combinado_com_anterior: bool = False
    letra: str = ''           # A, B... quando faz parte de exercícios combinados
    abre_grupo: bool = False  # veio logo depois do título "Exercícios combinados"
    tem_series: bool = False
    tem_carga: bool = False
    tem_intervalo: bool = False

    @property
    def completo(self):
        return self.tem_series or self.tem_carga or self.tem_intervalo or bool(self.instrucoes)

    # mesmos nomes do modelo ExercicioFicha, para as telas mostrarem os dois do mesmo jeito
    @property
    def series_planejadas(self):
        return self.series

    @property
    def repeticoes_planejadas(self):
        return self.repeticoes


@dataclass
class Leitura:
    exercicios: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def combinados(self):
        """Quantos grupos de exercícios combinados a série tem."""
        return sum(1 for e in self.exercicios if e.letra and not e.combinado_com_anterior)


def ler_series(texto):
    """'3x10+10' -> (3, 10, False); '3/10 cada lado' -> (3, 10, True). None se não entender."""
    achado = SERIES.search(sem_acento(texto))
    if not achado:
        return None
    series, repeticoes = int(achado.group(1)), int(achado.group(2))
    if not (1 <= series <= 20 and 1 <= repeticoes <= 200):
        return None
    return series, repeticoes, 'cada lado' in sem_acento(texto)


def ler_series_por_tempo(texto):
    """'3x30s' -> (3, 30, False); '2x1min cada lado' -> (2, 60, True). None se não for por tempo."""
    achado = SERIES_TEMPO.search(sem_acento(texto))
    if not achado:
        return None
    series, segundos = int(achado.group(1)), ler_intervalo(achado.group(2).replace('"', 's'))
    if not (1 <= series <= 20) or segundos is None:
        return None
    return series, segundos, 'cada lado' in sem_acento(texto)


def ler_carga(texto):
    """'15 kg' -> Decimal('15'); '12,5kg' -> Decimal('12.5')."""
    achado = NUMERO.search(texto)
    if not achado:
        return None
    try:
        carga = Decimal(achado.group().replace(',', '.'))
    except InvalidOperation:
        return None
    return carga if carga <= 1000 else None


def ler_intervalo(texto):
    """'60s' -> 60; '2min' -> 120; '1:30' -> 90; '90' -> 90."""
    limpo = sem_acento(texto).strip()
    achado = re.search(r'(\d+)\s*:\s*(\d{2})', limpo)
    if achado:
        segundos = int(achado.group(1)) * 60 + int(achado.group(2))
    else:
        achado = re.search(r'(\d+(?:[.,]\d+)?)\s*(min|m\b|minutos?)?', limpo)
        if not achado:
            return None
        valor = float(achado.group(1).replace(',', '.'))
        segundos = int(round(valor * 60)) if achado.group(2) else int(valor)
    return segundos if 0 < segundos <= 1800 else None


def _blocos(texto):
    bloco = []
    for linha in (texto or '').replace('\r\n', '\n').split('\n'):
        linha = ' '.join(linha.split())
        if linha:
            bloco.append(linha)
        elif bloco:
            yield bloco
            bloco = []
    if bloco:
        yield bloco


def _ler_campo(atual, nome_campo, valor, leitura):
    """Preenche um campo do exercício. Devolve True quando começam as instruções."""
    if nome_campo.startswith('serie') and ler_series_por_tempo(valor):
        atual.series, atual.tempo_segundos, atual.cada_lado = ler_series_por_tempo(valor)
        atual.series_texto, atual.tem_series = valor[:60], True
    elif nome_campo.startswith('serie') and SO_NUMERO.match(sem_acento(valor)):
        # só o número de séries; as repetições ou o tempo vêm em outra linha
        atual.series = max(min(int(SO_NUMERO.match(sem_acento(valor)).group(1)), 20), 1)
        atual.tem_series = True
    elif nome_campo in ('tempo', 'duracao'):
        segundos = ler_intervalo(valor)
        if segundos is None:
            leitura.avisos.append('%s: não entendi o tempo "%s".' % (atual.nome, valor))
        else:
            atual.tempo_segundos, atual.tem_series = segundos, True
            atual.cada_lado = atual.cada_lado or 'cada lado' in sem_acento(valor)
    elif nome_campo.startswith('serie') or nome_campo in ('repeticoes', 'reps'):
        lido = ler_series(valor)
        if lido:
            atual.series, atual.repeticoes, atual.cada_lado = lido
            atual.series_texto, atual.tem_series = valor[:60], True
        elif nome_campo in ('repeticoes', 'reps') and NUMERO.search(valor):
            atual.repeticoes = max(min(int(float(NUMERO.search(valor).group().replace(',', '.'))), 200), 1)
            atual.series_texto, atual.tem_series = valor[:60], True
        else:
            leitura.avisos.append('%s: não entendi as séries "%s"; usei %dx%d.' % (
                atual.nome, valor, SERIES_PADRAO, REPETICOES_PADRAO))
    elif nome_campo in ('carga', 'peso'):
        carga = ler_carga(valor)
        if carga is None:
            leitura.avisos.append('%s: não entendi a carga "%s"; usei 0 kg.' % (atual.nome, valor))
        else:
            atual.carga_kg, atual.tem_carga = carga, True
    elif nome_campo in ('intervalo', 'descanso'):
        segundos = ler_intervalo(valor)
        if segundos is None:
            leitura.avisos.append('%s: não entendi o intervalo "%s".' % (atual.nome, valor))
        else:
            atual.intervalo_segundos, atual.tem_intervalo = segundos, True
    else:  # instruções / observações
        if valor:
            atual.instrucoes = (atual.instrucoes + '\n' + valor).strip()
        return True
    return False


def _formar_grupos(exercicios):
    """
    Junta os exercícios combinados. Um grupo começa num exercício com a letra A (ou logo depois do
    título "Exercícios combinados") e segue pelas letras seguintes (B, C...). Sem letras, o grupo
    aberto pelo título vai até o primeiro exercício que traz as séries.
    """
    i = 0
    while i < len(exercicios):
        primeiro = exercicios[i]
        if not (primeiro.abre_grupo or primeiro.letra):
            i += 1
            continue
        membros = [primeiro]
        j = i + 1
        while j < len(exercicios):
            proximo = exercicios[j]
            if proximo.abre_grupo or proximo.letra == 'A':
                break
            if proximo.letra or (primeiro.abre_grupo and not membros[-1].completo):
                membros.append(proximo)
                j += 1
                continue
            break
        if len(membros) > 1:
            modelo = next((e for e in reversed(membros) if e.completo), None)
            for posicao, e in enumerate(membros):
                if modelo and modelo.tem_series and not e.tem_series:
                    e.series, e.repeticoes, e.series_texto = modelo.series, modelo.repeticoes, modelo.series_texto
                    e.tempo_segundos, e.cada_lado, e.tem_series = modelo.tempo_segundos, modelo.cada_lado, True
                if modelo and modelo.tem_intervalo and not e.tem_intervalo:
                    e.intervalo_segundos, e.tem_intervalo = modelo.intervalo_segundos, True
                if modelo and modelo.tem_carga and not e.tem_carga:
                    e.carga_kg = modelo.carga_kg
                if modelo and modelo.instrucoes and not e.instrucoes:
                    e.instrucoes = modelo.instrucoes
                e.letra = LETRAS[posicao % len(LETRAS)]
                e.combinado_com_anterior = posicao > 0
        else:
            primeiro.letra = ''  # letra sozinha não forma grupo
        i = j


def ler_texto(texto):
    """Lê o texto colado. Devolve os exercícios na ordem e os avisos do que foi preenchido no padrão."""
    leitura = Leitura()
    exercicios = leitura.exercicios
    abre_grupo = False  # o título "Exercícios combinados" vale para o próximo exercício

    for bloco in _blocos(texto):
        atual = None
        lendo_instrucoes = False
        for linha in bloco:
            chave = sem_acento(linha)
            if chave.startswith(ABRE_GRUPO):
                abre_grupo = True
                atual, lendo_instrucoes = None, False
                continue
            if chave.startswith(IGNORAR):
                continue

            campo = CAMPO.match(chave)
            if campo and atual is None:
                leitura.avisos.append('"%s" apareceu antes do nome de um exercício e foi ignorado.' % linha)
                continue
            if campo:
                lendo_instrucoes = _ler_campo(atual, campo.group(1), linha.split(':', 1)[1].strip(), leitura)
                continue

            if LETRA.match(linha) and atual is not None:
                atual.letra = linha
                continue

            if lendo_instrucoes:
                atual.instrucoes = (atual.instrucoes + '\n' + linha).strip()
                continue

            # Qualquer outra linha é o nome de um exercício novo
            if len(exercicios) >= LIMITE_EXERCICIOS:
                leitura.avisos.append('A série passou de %d exercícios; o resto foi ignorado.' % LIMITE_EXERCICIOS)
                break
            atual = ExercicioLido(nome=linha[:100], abre_grupo=abre_grupo)
            abre_grupo = False
            exercicios.append(atual)

    _formar_grupos(exercicios)
    for e in exercicios:
        if not e.tem_series:
            leitura.avisos.append('%s: sem "Séries"; usei %dx%d.' % (e.nome, SERIES_PADRAO, REPETICOES_PADRAO))
    return leitura
