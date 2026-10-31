import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


# Campo de chave primária usado em todas as tabelas (UUID, conforme modelagemDados.txt)
def chave_uuid():
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


OBJETIVOS = {
    'emagrecimento': 'Emagrecimento',
    'manutencao': 'Manutenção',
    'hipertrofia': 'Hipertrofia',
    'saude': 'Saúde e bem-estar',
}

INTENSIDADES = {
    'leve': 'Leve',
    'moderada': 'Moderada',
    'intensa': 'Intensa',
    'maxima': 'Máxima',
}

DIAS_DA_SEMANA = {
    'seg': 'Segunda-feira',
    'ter': 'Terça-feira',
    'qua': 'Quarta-feira',
    'qui': 'Quinta-feira',
    'sex': 'Sexta-feira',
    'sab': 'Sábado',
    'dom': 'Domingo',
}

# Duração média de cada treino que o usuário informa no perfil (minutos)
DURACOES_TREINO = [15, 30, 45, 60, 90, 120]


def dias_da_lista(texto):
    """'seg,qua' -> ['seg', 'qua'], na ordem da semana."""
    marcados = set(filter(None, (texto or '').split(',')))
    return [dia for dia in DIAS_DA_SEMANA if dia in marcados]


def nomes_curtos_dos_dias(texto):
    """'seg,qua' -> 'Seg, Qua'."""
    return ', '.join(DIAS_DA_SEMANA[dia][:3] for dia in dias_da_lista(texto))


# =====================================================================
# 1. DOMÍNIO DE IDENTIDADE E PERFIL
# =====================================================================

class Usuario(models.Model):
    id = chave_uuid()
    # Liga o perfil à conta de login do Django (e-mail e senha ficam no auth User)
    conta = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    nome_completo = models.CharField(max_length=150)
    apelido = models.CharField(max_length=20, blank=True)  # "Como quer ser chamado?"
    cpf = models.CharField(
        max_length=11,
        unique=True,  # também serve para login ("E-mail ou CPF")
        validators=[RegexValidator(r'^\d{11}$', 'Digite os 11 números do CPF, sem pontos.')],
    )
    celular = models.CharField(max_length=15)
    aceitou_termos = models.BooleanField(default=False)
    # Os campos abaixo são preenchidos no onboarding (perfil passos 1 e 2), por isso
    # ficam vazios entre o cadastro da conta e o fim do onboarding.
    data_nascimento = models.DateField(null=True, blank=True)  # usada para calcular a idade
    sexo_biologico = models.CharField(
        max_length=10,
        blank=True,
        choices={
            'masculino': 'Masculino',
            'feminino': 'Feminino',
        },
    )
    altura_cm = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(100), MaxValueValidator(250)],
    )
    peso_meta_kg = models.DecimalField(  # "Peso desejado (opcional)"
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    biotipo = models.CharField(
        max_length=10,
        blank=True,
        choices={
            'ectomorfo': 'Ectomorfo',
            'mesomorfo': 'Mesomorfo',
            'endomorfo': 'Endomorfo',
        },
    )
    avatar_url = models.URLField(max_length=2000, blank=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    # Última vez que a pessoa confirmou a rotina esportiva (o app pergunta de novo todo mês)
    rotina_confirmada_em = models.DateField(null=True, blank=True)

    def idade(self, hoje=None):
        if not self.data_nascimento:
            return None
        hoje = hoje or timezone.localdate()
        fez_aniversario = (hoje.month, hoje.day) >= (self.data_nascimento.month, self.data_nascimento.day)
        return hoje.year - self.data_nascimento.year - (0 if fez_aniversario else 1)

    def medida_atual(self):
        """Último peso registrado (o ponto mais recente do gráfico de evolução)."""
        return self.historicomedida_set.order_by('-data_registro').first()

    def meta_atual(self):
        return self.metanutricional_set.order_by('-data_inicio').first()

    def __str__(self):
        return self.apelido or self.nome_completo

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'usuário'
        verbose_name_plural = 'usuários'
        ordering = ['nome_completo']


class Esporte(models.Model):
    """Catálogo de esportes (musculação, corrida, futebol...)."""
    id = chave_uuid()
    nome = models.CharField(max_length=50, unique=True)
    # Gasto energético de referência (MET), usado no cálculo do gasto dos esportes
    met = models.DecimalField(max_digits=4, decimal_places=1)

    def __str__(self):
        return self.nome

    class Meta:
        db_table = 'esportes'
        verbose_name = 'esporte'
        verbose_name_plural = 'esportes'
        ordering = ['nome']


class EsporteUsuario(models.Model):
    """O que o usuário pratica, com que frequência e intensidade (perfil passo 3)."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='esportes')
    esporte = models.ForeignKey(Esporte, on_delete=models.PROTECT)
    frequencia_semanal = models.IntegerField(  # 7 = diário
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    intensidade = models.CharField(max_length=10, choices=INTENSIDADES)
    duracao_minutos = models.PositiveSmallIntegerField(  # média de cada treino
        default=60,
        choices=[(m, '%d min' % m) for m in DURACOES_TREINO],
    )
    # Dias fixos, ex.: "seg,qua". Os outros treinos da semana ficam livres (em qualquer dia).
    dias_fixos = models.CharField(max_length=27, blank=True)

    def __str__(self):
        return '%s: %s %dx/semana' % (self.usuario, self.esporte, self.frequencia_semanal)

    def lista_dias_fixos(self):
        return dias_da_lista(self.dias_fixos)

    @property
    def treinos_livres(self):
        return max(self.frequencia_semanal - len(self.lista_dias_fixos()), 0)

    class Meta:
        db_table = 'esportes_usuario'
        verbose_name = 'esporte do usuário'
        verbose_name_plural = 'esportes do usuário'
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'esporte'], name='esporte_unico_por_usuario'),
        ]


# =====================================================================
# 2. DOMÍNIO DE EVOLUÇÃO (histórico para os gráficos)
# =====================================================================

class HistoricoMedida(models.Model):
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    data_registro = models.DateTimeField()  # eixo X do gráfico
    peso_kg = models.DecimalField(  # eixo Y do gráfico
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('30')), MaxValueValidator(Decimal('300'))],
    )
    objetivo_momento = models.CharField(max_length=15, choices=OBJETIVOS)
    foto_shape_url = models.URLField(max_length=2000, blank=True)

    def __str__(self):
        return '%s: %s kg em %s' % (self.usuario, self.peso_kg, self.data_registro.date())

    class Meta:
        db_table = 'historico_medidas'
        verbose_name = 'histórico de medida'
        verbose_name_plural = 'histórico de medidas'
        ordering = ['usuario', '-data_registro']


# =====================================================================
# 3. DOMÍNIO DE NUTRIÇÃO
# =====================================================================

class MetaNutricional(models.Model):
    """Resultado do cálculo de metas (TMB + esportes + objetivo)."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    data_inicio = models.DateField()
    meta_agua_ml = models.IntegerField(validators=[MinValueValidator(0)])
    meta_calorias = models.IntegerField(validators=[MinValueValidator(0)])
    meta_proteina_g = models.DecimalField(max_digits=6, decimal_places=1)
    meta_carbo_g = models.DecimalField(max_digits=6, decimal_places=1)
    meta_gordura_g = models.DecimalField(max_digits=6, decimal_places=1)

    def __str__(self):
        return 'Meta de %s desde %s' % (self.usuario, self.data_inicio)

    class Meta:
        db_table = 'metas_nutricionais'
        verbose_name = 'meta nutricional'
        verbose_name_plural = 'metas nutricionais'
        ordering = ['usuario', '-data_inicio']


class Alimento(models.Model):
    """Catálogo central de alimentos (populado com a tabela TACO/UNICAMP)."""
    id = chave_uuid()
    nome = models.CharField(max_length=150)
    porcao_padrao = models.CharField(max_length=50)  # ex.: "100g", "1 colher de sopa"
    porcao_gramas = models.DecimalField(  # quantos gramas tem a porção padrão
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    # Valores nutricionais de UMA porção padrão
    kcal = models.DecimalField(max_digits=7, decimal_places=2)
    proteina_g = models.DecimalField(max_digits=6, decimal_places=2)
    carbo_g = models.DecimalField(max_digits=6, decimal_places=2)
    gordura_g = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return '%s (%s)' % (self.nome, self.porcao_padrao)

    class Meta:
        db_table = 'catalogo_alimentos'
        verbose_name = 'alimento'
        verbose_name_plural = 'catálogo de alimentos'
        ordering = ['nome']


class MedidaCaseira(models.Model):
    """Porções do dia a dia: "1 colher de sopa", "1 concha", "1 fatia"..."""
    id = chave_uuid()
    alimento = models.ForeignKey(Alimento, on_delete=models.CASCADE, related_name='medidas')
    nome = models.CharField(max_length=50)
    gramas = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    def __str__(self):
        return '%s de %s (%s g)' % (self.nome, self.alimento.nome, self.gramas)

    class Meta:
        db_table = 'medidas_caseiras'
        verbose_name = 'medida caseira'
        verbose_name_plural = 'medidas caseiras'
        ordering = ['alimento', 'gramas']


class RefeicaoPersonalizada(models.Model):
    """Os "combos" do usuário, ex.: Vitamina Pós-Treino."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    nome_refeicao = models.CharField(max_length=100)

    def __str__(self):
        return self.nome_refeicao

    class Meta:
        db_table = 'refeicoes_personalizadas'
        verbose_name = 'refeição personalizada'
        verbose_name_plural = 'refeições personalizadas'
        ordering = ['usuario', 'nome_refeicao']


class RefeicaoPersonalizadaItem(models.Model):
    """O que vai dentro de cada combo."""
    id = chave_uuid()
    refeicao_personalizada = models.ForeignKey(
        RefeicaoPersonalizada,
        on_delete=models.CASCADE,  # apaga os itens ao apagar a refeição
        related_name='itens',
    )
    alimento = models.ForeignKey(
        Alimento,
        on_delete=models.PROTECT,  # não deixa apagar alimento usado em refeição
    )
    quantidade_multiplicador = models.DecimalField(  # ex.: 2.0 = duas porções padrão
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    def __str__(self):
        return '%sx %s' % (self.quantidade_multiplicador, self.alimento.nome)

    class Meta:
        db_table = 'refeicoes_personalizadas_itens'
        verbose_name = 'item da refeição'
        verbose_name_plural = 'itens da refeição'


class DiarioConsumo(models.Model):
    """O dia a dia real: água bebida e check-in da dieta."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    data_referencia = models.DateField()
    total_agua_consumida_ml = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    status_dieta_cumprida = models.BooleanField(default=False)

    def __str__(self):
        return '%s em %s' % (self.usuario, self.data_referencia)

    class Meta:
        db_table = 'diario_consumo'
        verbose_name = 'diário de consumo'
        verbose_name_plural = 'diários de consumo'
        ordering = ['usuario', '-data_referencia']
        # um registro por usuário por dia
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'data_referencia'],
                name='diario_unico_por_dia',
            ),
        ]


class RegistroRefeicao(models.Model):
    """Uma refeição comida num dia (café da manhã, almoço...)."""
    id = chave_uuid()
    diario = models.ForeignKey(DiarioConsumo, on_delete=models.CASCADE, related_name='refeicoes')
    tipo_refeicao = models.CharField(
        max_length=15,
        choices={
            'cafe_manha': 'Café da manhã',
            'lanche_manha': 'Lanche da manhã',
            'almoco': 'Almoço',
            'lanche_tarde': 'Lanche da tarde',
            'jantar': 'Jantar',
            'ceia': 'Ceia',
        },
    )
    horario = models.DateTimeField()
    # Preenchido quando a refeição foi lançada a partir de um combo salvo
    refeicao_personalizada = models.ForeignKey(
        RefeicaoPersonalizada,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return '%s - %s' % (self.diario, self.get_tipo_refeicao_display())

    class Meta:
        db_table = 'registros_refeicao'
        verbose_name = 'refeição registrada'
        verbose_name_plural = 'refeições registradas'
        ordering = ['-horario']


class RegistroRefeicaoItem(models.Model):
    """Cada alimento comido numa refeição registrada."""
    id = chave_uuid()
    registro = models.ForeignKey(RegistroRefeicao, on_delete=models.CASCADE, related_name='itens')
    alimento = models.ForeignKey(Alimento, on_delete=models.PROTECT)
    # Se vazio, a quantidade é em porções padrão do alimento
    medida_caseira = models.ForeignKey(MedidaCaseira, on_delete=models.PROTECT, null=True, blank=True)
    quantidade = models.DecimalField(  # ex.: 2 colheres, 1.5 porção
        max_digits=6,
        decimal_places=2,
        default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    def gramas(self):
        if self.medida_caseira:
            return self.quantidade * self.medida_caseira.gramas
        return self.quantidade * self.alimento.porcao_gramas

    def macros(self):
        """kcal e macronutrientes do que foi comido, proporcional aos gramas."""
        fator = self.gramas() / self.alimento.porcao_gramas
        return {
            'kcal': self.alimento.kcal * fator,
            'proteina_g': self.alimento.proteina_g * fator,
            'carbo_g': self.alimento.carbo_g * fator,
            'gordura_g': self.alimento.gordura_g * fator,
        }

    def __str__(self):
        return '%s g de %s' % (self.gramas(), self.alimento.nome)

    class Meta:
        db_table = 'registros_refeicao_itens'
        verbose_name = 'alimento consumido'
        verbose_name_plural = 'alimentos consumidos'


# =====================================================================
# 4. DOMÍNIO DE TREINO E ATIVIDADES
# =====================================================================

class FichaTreino(models.Model):
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    nome_ficha = models.CharField(max_length=100)  # ex.: "Treino A - Peito e Ombro"
    dias_semana = models.CharField(max_length=27, blank=True)  # planejamento semanal, ex.: "seg,qui"
    ativa = models.BooleanField(default=True)  # inativa: some da lista de treinos, mas não é apagada
    criada_em = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return self.nome_ficha

    def lista_dias(self):
        return dias_da_lista(self.dias_semana)

    def nomes_dos_dias(self):
        return nomes_curtos_dos_dias(self.dias_semana)

    class Meta:
        db_table = 'fichas_treino'
        verbose_name = 'ficha de treino'
        verbose_name_plural = 'fichas de treino'
        ordering = ['usuario', 'nome_ficha']


class ExercicioFicha(models.Model):
    id = chave_uuid()
    ficha = models.ForeignKey(FichaTreino, on_delete=models.CASCADE, related_name='exercicios')
    nome_exercicio = models.CharField(max_length=100)
    ordem_execucao = models.IntegerField(validators=[MinValueValidator(1)])
    series_planejadas = models.IntegerField(default=3, validators=[MinValueValidator(1)])
    repeticoes_planejadas = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    # Exercício por tempo (prancha, isometria, estabilidade): segundos de cada série.
    # Vazio = exercício por repetições.
    tempo_segundos = models.PositiveIntegerField(null=True, blank=True)
    # Como o treino veio escrito, ex.: "3x10+10" ou "3/10 cada lado"
    series_texto = models.CharField(max_length=60, blank=True)
    cada_lado = models.BooleanField(default=False)  # exercício unilateral: as repetições valem para cada lado
    carga_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    intervalo_segundos = models.PositiveIntegerField(null=True, blank=True)
    instrucoes = models.TextField(blank=True)
    # Feito em sequência com o exercício anterior (bi-set): A, B, C... alternados
    combinado_com_anterior = models.BooleanField(default=False)
    imagem = models.ImageField(upload_to='exercicios/', blank=True)
    video_url = models.URLField('link do vídeo', blank=True)

    def __str__(self):
        return '%d. %s' % (self.ordem_execucao, self.nome_exercicio)

    class Meta:
        db_table = 'exercicios_ficha'
        verbose_name = 'exercício da ficha'
        verbose_name_plural = 'exercícios da ficha'
        ordering = ['ficha', 'ordem_execucao']


class SessaoAtividade(models.Model):
    """Um treino ou partida feito de verdade, de qualquer esporte."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='sessoes')
    esporte = models.ForeignKey(Esporte, on_delete=models.PROTECT)
    ficha = models.ForeignKey(  # preenchido em treinos de musculação
        FichaTreino,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    inicio = models.DateTimeField()
    duracao_minutos = models.IntegerField(validators=[MinValueValidator(1)])
    intensidade = models.CharField(max_length=10, choices=INTENSIDADES)
    distancia_km = models.DecimalField(  # corrida, ciclismo, natação
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    def __str__(self):
        return '%s - %s em %s' % (self.usuario, self.esporte, self.inicio.date())

    class Meta:
        db_table = 'sessoes_atividade'
        verbose_name = 'sessão de atividade'
        verbose_name_plural = 'sessões de atividade'
        ordering = ['-inicio']


class SerieExecutada(models.Model):
    """Onde fica salva a carga de cada série."""
    id = chave_uuid()
    sessao = models.ForeignKey(SessaoAtividade, on_delete=models.CASCADE, related_name='series')
    exercicio = models.ForeignKey(ExercicioFicha, on_delete=models.CASCADE, related_name='series')
    numero_serie = models.IntegerField(validators=[MinValueValidator(1)])
    carga_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    repeticoes = models.IntegerField(validators=[MinValueValidator(1)])

    def __str__(self):
        return '%s: %s kg x %d' % (self.exercicio.nome_exercicio, self.carga_kg, self.repeticoes)

    class Meta:
        db_table = 'series_executadas_historico'
        verbose_name = 'série executada'
        verbose_name_plural = 'séries executadas'
        ordering = ['-sessao__inicio', 'exercicio', 'numero_serie']


# =====================================================================
# 5. DOMÍNIO DE GAMIFICAÇÃO SOCIAL (Gymrats)
# =====================================================================

# Patamares do Documento de Regras de Negócio (XP mínimo, nível, nome, selo)
NIVEIS = [
    (10000, 5, 'Lenda', 'Diamante'),
    (4000, 4, 'Atleta', 'Ouro'),
    (1500, 3, 'Amador Dedicado', 'Prata'),
    (500, 2, 'Praticante', 'Bronze'),
    (0, 1, 'Iniciante', 'Semente'),
]


class PerfilGamificacao(models.Model):
    id = chave_uuid()
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)  # um perfil por usuário
    streak_atual = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    pontos_experiencia = models.IntegerField(default=0, validators=[MinValueValidator(0)])  # XP vitalício
    escudos_descanso = models.IntegerField(default=0, validators=[MinValueValidator(0)])  # 1 a cada 15 dias de streak
    ultimo_dia_ativo = models.DateField(null=True, blank=True)

    def nivel(self):
        for xp_minimo, numero, nome, selo in NIVEIS:
            if self.pontos_experiencia >= xp_minimo:
                return {'numero': numero, 'nome': nome, 'selo': selo}

    def __str__(self):
        return '%s - %d XP' % (self.usuario, self.pontos_experiencia)

    class Meta:
        db_table = 'perfil_gamificacao'
        verbose_name = 'perfil de gamificação'
        verbose_name_plural = 'perfis de gamificação'
        ordering = ['-pontos_experiencia']


# Pontos de cada ação (Documento de Regras de Negócio, seção 3)
PONTOS_POR_ACAO = {
    'treino': 50,
    'atividade_secundaria': 20,
    'recorde_pessoal': 30,
    'checkin_refeicao': 10,
    'dieta_perfeita': 40,
    'meta_agua': 15,
    'combo_saude': 30,
}


class RegistroXP(models.Model):
    """Cada ganho de XP. A soma da semana forma o Ranking da Galera."""
    id = chave_uuid()
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='registros_xp')
    acao = models.CharField(
        max_length=25,
        choices={
            'treino': 'Registrar partida / treino',
            'atividade_secundaria': 'Atividade secundária',
            'recorde_pessoal': 'Recorde pessoal',
            'checkin_refeicao': 'Check-in de refeição',
            'dieta_perfeita': 'Check-in de dieta perfeita',
            'meta_agua': 'Meta de água atingida',
            'combo_saude': 'Combo saúde (treino + dieta)',
        },
    )
    pontos = models.IntegerField()  # já com a penalidade de 50% para check-in retroativo
    data_referencia = models.DateField()  # dia a que os pontos pertencem
    criado_em = models.DateTimeField(auto_now_add=True)
    sessao = models.ForeignKey(SessaoAtividade, on_delete=models.SET_NULL, null=True, blank=True)
    refeicao = models.ForeignKey(RegistroRefeicao, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return '%s +%d XP (%s)' % (self.usuario, self.pontos, self.get_acao_display())

    class Meta:
        db_table = 'historico_xp'
        verbose_name = 'registro de XP'
        verbose_name_plural = 'histórico de XP'
        ordering = ['-data_referencia', '-criado_em']


class Amizade(models.Model):
    id = chave_uuid()  # o Django exige uma chave primária própria
    usuario_1 = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='amizades_enviadas')
    usuario_2 = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='amizades_recebidas')

    def __str__(self):
        return '%s & %s' % (self.usuario_1, self.usuario_2)

    class Meta:
        db_table = 'amizades'
        verbose_name = 'amizade'
        verbose_name_plural = 'amizades'
        constraints = [
            models.UniqueConstraint(fields=['usuario_1', 'usuario_2'], name='amizade_unica'),
            models.CheckConstraint(
                condition=~models.Q(usuario_1=models.F('usuario_2')),
                name='amizade_sem_si_mesmo',
            ),
        ]


class Grupo(models.Model):
    """Grupo privado de amigos com ranking próprio."""
    id = chave_uuid()
    nome = models.CharField(max_length=60)
    descricao = models.TextField(blank=True)
    criador = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='grupos_criados')
    codigo_convite = models.CharField(max_length=12, unique=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    def ranking_semanal(self, dia):
        """Membros ordenados pelo XP da semana (segunda a domingo) que contém `dia`."""
        segunda = dia - timedelta(days=dia.weekday())
        domingo = segunda + timedelta(days=6)
        xp_da_semana = Sum(
            'registros_xp__pontos',
            filter=models.Q(registros_xp__data_referencia__range=(segunda, domingo)),
        )
        return (
            Usuario.objects.filter(grupos__grupo=self)
            .annotate(xp_semana=Coalesce(xp_da_semana, 0))
            .order_by('-xp_semana', 'nome_completo')
        )

    def __str__(self):
        return self.nome

    class Meta:
        db_table = 'grupos'
        verbose_name = 'grupo'
        verbose_name_plural = 'grupos'
        ordering = ['nome']


class MembroGrupo(models.Model):
    id = chave_uuid()
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name='membros')
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='grupos')
    papel = models.CharField(
        max_length=10,
        choices={
            'admin': 'Administrador',
            'membro': 'Membro',
        },
        default='membro',
    )
    data_entrada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '%s em %s' % (self.usuario, self.grupo)

    class Meta:
        db_table = 'membros_grupo'
        verbose_name = 'membro do grupo'
        verbose_name_plural = 'membros do grupo'
        constraints = [
            models.UniqueConstraint(fields=['grupo', 'usuario'], name='membro_unico_por_grupo'),
        ]


class Desafio(models.Model):
    """Desafio personalizável dentro de um grupo."""
    id = chave_uuid()
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE, related_name='desafios')
    criador = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='desafios_criados')
    nome = models.CharField(max_length=80)  # ex.: "Quem treina mais em outubro"
    descricao = models.TextField(blank=True)
    metrica = models.CharField(
        max_length=15,
        choices={
            'xp': 'Mais XP',
            'sessoes': 'Mais treinos/partidas',
            'dieta': 'Mais dias de dieta perfeita',
            'agua': 'Mais dias com meta de água',
        },
    )
    data_inicio = models.DateField()
    data_fim = models.DateField()

    def __str__(self):
        return '%s (%s)' % (self.nome, self.grupo)

    class Meta:
        db_table = 'desafios'
        verbose_name = 'desafio'
        verbose_name_plural = 'desafios'
        ordering = ['-data_inicio']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(data_fim__gte=models.F('data_inicio')),
                name='desafio_fim_depois_do_inicio',
            ),
        ]


class ParticipanteDesafio(models.Model):
    id = chave_uuid()
    desafio = models.ForeignKey(Desafio, on_delete=models.CASCADE, related_name='participantes')
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='desafios')
    data_entrada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '%s no desafio %s' % (self.usuario, self.desafio.nome)

    class Meta:
        db_table = 'participantes_desafio'
        verbose_name = 'participante do desafio'
        verbose_name_plural = 'participantes do desafio'
        constraints = [
            models.UniqueConstraint(fields=['desafio', 'usuario'], name='participante_unico_por_desafio'),
        ]
