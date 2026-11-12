"""
Diário alimentar: registro de refeições (RF09), registro por porções (RF10), histórico (RF11)
e saldo do dia contra a meta (RF12).

Regras do "Documento de Especificação de Regras de Negócio":
- Check-in de dieta perfeita = encerrar o dia dentro da meta de calorias e macros.
  Aqui, "dentro da meta" é ficar entre 90% e 110% da meta de calorias e de cada macronutriente.
- Não dá para registrar dias futuros; dias passados podem ser preenchidos.
"""
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from saude.models import (
    Alimento,
    DiarioConsumo,
    MetaNutricional,
    RefeicaoPersonalizada,
    RefeicaoPersonalizadaItem,
    RegistroRefeicao,
    RegistroRefeicaoItem,
)

TIPOS_REFEICAO = RegistroRefeicao._meta.get_field('tipo_refeicao').choices
NOMES_REFEICAO = dict(TIPOS_REFEICAO)

MACROS = ('kcal', 'proteina_g', 'carbo_g', 'gordura_g')
CAMPO_DA_META = {
    'kcal': 'meta_calorias',
    'proteina_g': 'meta_proteina_g',
    'carbo_g': 'meta_carbo_g',
    'gordura_g': 'meta_gordura_g',
}
TOLERANCIA = Decimal('0.10')  # 90% a 110% da meta
AGUA_MAXIMA_ML = 10000


class DiaFuturo(Exception):
    """Tentativa de registrar algo num dia que ainda não chegou."""


def hoje():
    return timezone.localdate()


def validar_dia(data):
    if data > hoje():
        raise DiaFuturo('Não dá para registrar dias futuros.')


def zerado():
    return {macro: Decimal('0') for macro in MACROS}


def somar(itens):
    total = zerado()
    for item in itens:
        for macro, valor in item.macros().items():
            total[macro] += valor
    return total


def meta_do_dia(usuario, data):
    """
    A meta que valia naquele dia (a mais recente com início até a data), ajustada pelos treinos feitos
    no dia (balanço calórico, Sprint 9: a média dos esportes do perfil é trocada pelo gasto real).
    """
    from balanco.servicos import meta_com_treinos

    meta = MetaNutricional.objects.filter(usuario=usuario, data_inicio__lte=data).order_by('-data_inicio').first()
    return meta_com_treinos(usuario, data, meta or usuario.meta_atual())


def refeicao_sugerida(agora=None):
    """Tipo de refeição mais provável pelo horário (usado como padrão ao adicionar)."""
    hora = (agora or timezone.localtime()).hour
    if hora < 10:
        return 'cafe_manha'
    if hora < 12:
        return 'lanche_manha'
    if hora < 15:
        return 'almoco'
    if hora < 18:
        return 'lanche_tarde'
    if hora < 21:
        return 'jantar'
    return 'ceia'


def horario_para(data):
    """Hoje: agora. Dias passados: meio-dia daquele dia."""
    if data == hoje():
        return timezone.now()
    return timezone.make_aware(datetime.combine(data, time(12)))


# =====================================================================
# Resumo do dia
# =====================================================================

@dataclass
class RefeicaoDoDia:
    tipo: str
    nome: str
    registros: list
    itens: list
    total: dict


@dataclass
class ResumoDoDia:
    data: object
    diario: object
    meta: object
    refeicoes: list
    total: dict

    @property
    def agua_ml(self):
        return self.diario.total_agua_consumida_ml if self.diario else 0

    @property
    def tem_itens(self):
        return any(r.itens for r in self.refeicoes)

    @property
    def dieta_confirmada(self):
        return bool(self.diario and self.diario.status_dieta_cumprida)

    def alvo(self, macro):
        return Decimal(getattr(self.meta, CAMPO_DA_META[macro])) if self.meta else Decimal('0')

    def percentual(self, macro):
        alvo = self.alvo(macro)
        return int(self.total[macro] * 100 / alvo) if alvo else 0

    def restante(self, macro):
        return self.alvo(macro) - self.total[macro]

    @property
    def percentual_kcal(self):
        return self.percentual('kcal')

    @property
    def restante_kcal(self):
        return self.restante('kcal')

    @property
    def percentual_agua(self):
        if not self.meta or not self.meta.meta_agua_ml:
            return 0
        return int(self.agua_ml * 100 / self.meta.meta_agua_ml)

    @property
    def meta_agua_atingida(self):
        return bool(self.meta) and self.agua_ml >= self.meta.meta_agua_ml

    @property
    def dentro_da_meta(self):
        if not self.meta or not self.tem_itens:
            return False
        for macro in MACROS:
            alvo = self.alvo(macro)
            if alvo and not (alvo * (1 - TOLERANCIA) <= self.total[macro] <= alvo * (1 + TOLERANCIA)):
                return False
        return True

    def barras(self):
        """Dados prontos para os cartões de macros do template."""
        return [
            {'macro': macro, 'consumido': self.total[macro], 'alvo': self.alvo(macro),
             'percentual': self.percentual(macro), 'largura': min(self.percentual(macro), 100)}
            for macro in ('proteina_g', 'carbo_g', 'gordura_g')
        ]


def resumo_do_dia(usuario, data):
    diario = DiarioConsumo.objects.filter(usuario=usuario, data_referencia=data).first()
    registros = []
    if diario:
        registros = list(
            diario.refeicoes.order_by('horario')
            .prefetch_related('itens__alimento', 'itens__medida_caseira')
        )
    refeicoes = []
    for tipo, nome in TIPOS_REFEICAO:
        do_tipo = [r for r in registros if r.tipo_refeicao == tipo]
        itens = [item for r in do_tipo for item in r.itens.all()]
        refeicoes.append(RefeicaoDoDia(tipo=tipo, nome=nome, registros=do_tipo, itens=itens, total=somar(itens)))
    total = zerado()
    for refeicao in refeicoes:
        for macro in MACROS:
            total[macro] += refeicao.total[macro]
    return ResumoDoDia(data=data, diario=diario, meta=meta_do_dia(usuario, data), refeicoes=refeicoes, total=total)


def revisar_checkin(usuario, diario):
    """Se o dia saiu da meta depois do check-in de dieta perfeita, o check-in é desfeito."""
    if diario.status_dieta_cumprida and not resumo_do_dia(usuario, diario.data_referencia).dentro_da_meta:
        diario.status_dieta_cumprida = False
        diario.save(update_fields=['status_dieta_cumprida'])


# =====================================================================
# Registrar e remover alimentos
# =====================================================================

def registro_da_refeicao(diario, tipo):
    """A refeição daquele tipo no dia (cria se ainda não existe)."""
    registro = diario.refeicoes.filter(tipo_refeicao=tipo).order_by('horario').first()
    if registro is None:
        registro = RegistroRefeicao.objects.create(
            diario=diario, tipo_refeicao=tipo, horario=horario_para(diario.data_referencia),
        )
    return registro


@transaction.atomic
def registrar_item(usuario, data, tipo, alimento, quantidade, medida=None):
    """Lança um alimento numa refeição. Sem medida caseira, a quantidade é em porções padrão (100 g)."""
    validar_dia(data)
    diario, _ = DiarioConsumo.objects.get_or_create(usuario=usuario, data_referencia=data)
    item = RegistroRefeicaoItem.objects.create(
        registro=registro_da_refeicao(diario, tipo), alimento=alimento, medida_caseira=medida, quantidade=quantidade,
    )
    revisar_checkin(usuario, diario)
    return item


@transaction.atomic
def remover_item(usuario, item_id):
    item = RegistroRefeicaoItem.objects.select_related('registro__diario').get(
        id=item_id, registro__diario__usuario=usuario,
    )
    registro, diario = item.registro, item.registro.diario
    item.delete()
    if not registro.itens.exists():
        registro.delete()
    revisar_checkin(usuario, diario)
    return diario


# =====================================================================
# Água e check-in de dieta perfeita
# =====================================================================

def adicionar_agua(usuario, data, ml):
    validar_dia(data)
    diario, _ = DiarioConsumo.objects.get_or_create(usuario=usuario, data_referencia=data)
    diario.total_agua_consumida_ml = min(max(diario.total_agua_consumida_ml + ml, 0), AGUA_MAXIMA_ML)
    diario.save(update_fields=['total_agua_consumida_ml'])
    return diario


def confirmar_dieta(usuario, data):
    """Check-in de dieta perfeita. Só confirma se o dia estiver dentro da meta."""
    validar_dia(data)
    resumo = resumo_do_dia(usuario, data)
    if not resumo.dentro_da_meta:
        return False
    resumo.diario.status_dieta_cumprida = True
    resumo.diario.save(update_fields=['status_dieta_cumprida'])
    return True


def desfazer_dieta(usuario, data):
    DiarioConsumo.objects.filter(usuario=usuario, data_referencia=data).update(status_dieta_cumprida=False)


# =====================================================================
# Combos ("Café da manhã padrão")
# =====================================================================

def macros_do_combo(combo):
    total = zerado()
    for item in combo.itens.all():
        fator = item.quantidade_multiplicador
        total['kcal'] += item.alimento.kcal * fator
        total['proteina_g'] += item.alimento.proteina_g * fator
        total['carbo_g'] += item.alimento.carbo_g * fator
        total['gordura_g'] += item.alimento.gordura_g * fator
    return total


def combos_do_usuario(usuario):
    combos = list(
        RefeicaoPersonalizada.objects.filter(usuario=usuario)
        .prefetch_related('itens__alimento').order_by('nome_refeicao')
    )
    for combo in combos:
        combo.total = macros_do_combo(combo)
    return combos


@transaction.atomic
def salvar_combo(usuario, registro_id, nome):
    """Guarda os alimentos de uma refeição registrada como combo reutilizável."""
    registro = RegistroRefeicao.objects.get(id=registro_id, diario__usuario=usuario)
    itens = list(registro.itens.select_related('alimento', 'medida_caseira'))
    if not itens:
        raise ValueError('Essa refeição não tem alimentos.')
    combo = RefeicaoPersonalizada.objects.create(usuario=usuario, nome_refeicao=nome)
    RefeicaoPersonalizadaItem.objects.bulk_create([
        RefeicaoPersonalizadaItem(
            refeicao_personalizada=combo,
            alimento=item.alimento,
            # o combo guarda a quantidade em porções padrão (ex.: 150 g de arroz = 1,5 porção de 100 g)
            quantidade_multiplicador=(item.gramas() / item.alimento.porcao_gramas).quantize(Decimal('0.01')),
        )
        for item in itens
    ])
    registro.refeicao_personalizada = combo
    registro.save(update_fields=['refeicao_personalizada'])
    return combo


@transaction.atomic
def usar_combo(usuario, data, tipo, combo_id):
    """Lança todos os alimentos de um combo numa refeição do dia."""
    validar_dia(data)
    combo = RefeicaoPersonalizada.objects.get(id=combo_id, usuario=usuario)
    diario, _ = DiarioConsumo.objects.get_or_create(usuario=usuario, data_referencia=data)
    registro = registro_da_refeicao(diario, tipo)
    registro.refeicao_personalizada = combo
    registro.save(update_fields=['refeicao_personalizada'])
    RegistroRefeicaoItem.objects.bulk_create([
        RegistroRefeicaoItem(registro=registro, alimento=item.alimento, quantidade=item.quantidade_multiplicador)
        for item in combo.itens.select_related('alimento')
    ])
    revisar_checkin(usuario, diario)
    return combo


def excluir_combo(usuario, combo_id):
    RefeicaoPersonalizada.objects.filter(id=combo_id, usuario=usuario).delete()


# =====================================================================
# Busca de alimentos
# =====================================================================

def normalizar(texto):
    """Minúsculas e sem acento: "Feijão" e "feijao" viram a mesma coisa."""
    sem_acento = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')
    return sem_acento.lower()


def buscar_alimentos(texto, limite=25):
    """
    Procura no catálogo TACO por todas as palavras digitadas, sem ligar para acento.
    Mostra primeiro os alimentos que têm medida caseira e os que começam com a primeira palavra.
    """
    palavras = normalizar(texto).replace(',', ' ').split()
    if not palavras:
        return []
    encontrados = []
    for alimento in Alimento.objects.annotate(qtd_medidas=Count('medidas')):
        nome = normalizar(alimento.nome)
        if all(palavra in nome for palavra in palavras):
            encontrados.append(alimento)
    encontrados.sort(key=lambda a: (
        a.qtd_medidas == 0,
        not normalizar(a.nome).startswith(palavras[0]),
        len(a.nome),
    ))
    return encontrados[:limite]


def alimentos_recentes(usuario, limite=8, dias=30):
    """Os alimentos que o usuário lançou nos últimos dias, do mais recente para o mais antigo."""
    desde = hoje() - timedelta(days=dias)
    ids = (
        RegistroRefeicaoItem.objects
        .filter(registro__diario__usuario=usuario, registro__diario__data_referencia__gte=desde)
        .values('alimento').annotate(ultimo=Max('registro__horario')).order_by('-ultimo')
        .values_list('alimento', flat=True)[:limite]
    )
    por_id = Alimento.objects.in_bulk(list(ids))
    return [por_id[i] for i in ids if i in por_id]


# =====================================================================
# Histórico
# =====================================================================

def historico(usuario, dias=14, ate=None):
    """Um resumo por dia (do mais recente para o mais antigo)."""
    ate = ate or hoje()
    return [resumo_do_dia(usuario, ate - timedelta(days=n)) for n in range(dias)]
