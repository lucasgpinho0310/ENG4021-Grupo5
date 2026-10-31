from django.contrib import admin

from .models import (
    Alimento,
    Amizade,
    Desafio,
    DiarioConsumo,
    Esporte,
    EsporteUsuario,
    ExercicioFicha,
    FichaTreino,
    Grupo,
    HistoricoMedida,
    MedidaCaseira,
    MembroGrupo,
    MetaNutricional,
    ParticipanteDesafio,
    PerfilGamificacao,
    RefeicaoPersonalizada,
    RefeicaoPersonalizadaItem,
    RegistroRefeicao,
    RegistroRefeicaoItem,
    RegistroXP,
    SerieExecutada,
    SessaoAtividade,
    Usuario,
)


# ----- Identidade e perfil -----

class EsporteUsuarioInline(admin.TabularInline):
    model = EsporteUsuario
    extra = 1


class UsuarioAdmin(admin.ModelAdmin):
    list_display = ['nome_completo', 'apelido', 'cpf', 'sexo_biologico', 'altura_cm', 'biotipo', 'data_cadastro']
    list_filter = ['sexo_biologico', 'biotipo']
    search_fields = ['nome_completo', 'apelido', 'cpf']
    inlines = [EsporteUsuarioInline]

admin.site.register(Usuario, UsuarioAdmin)


class EsporteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'met']
    search_fields = ['nome']

admin.site.register(Esporte, EsporteAdmin)


# ----- Evolução -----

class HistoricoMedidaAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'data_registro', 'peso_kg', 'objetivo_momento']
    ordering = ['usuario', '-data_registro']
    list_filter = ['usuario', 'objetivo_momento']

admin.site.register(HistoricoMedida, HistoricoMedidaAdmin)


# ----- Nutrição -----

class MetaNutricionalAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'data_inicio', 'meta_calorias', 'meta_proteina_g',
                    'meta_carbo_g', 'meta_gordura_g', 'meta_agua_ml']
    list_filter = ['usuario']

admin.site.register(MetaNutricional, MetaNutricionalAdmin)


class MedidaCaseiraInline(admin.TabularInline):
    model = MedidaCaseira
    extra = 1


class AlimentoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'porcao_padrao', 'kcal', 'proteina_g', 'carbo_g', 'gordura_g']
    ordering = ['nome']
    search_fields = ['nome']  # caixa de busca: são ~600 alimentos
    inlines = [MedidaCaseiraInline]

admin.site.register(Alimento, AlimentoAdmin)


class MedidaCaseiraAdmin(admin.ModelAdmin):
    list_display = ['alimento', 'nome', 'gramas']
    search_fields = ['alimento__nome', 'nome']
    autocomplete_fields = ['alimento']

admin.site.register(MedidaCaseira, MedidaCaseiraAdmin)


# Mostra os itens dentro da própria tela da refeição
class RefeicaoPersonalizadaItemInline(admin.TabularInline):
    model = RefeicaoPersonalizadaItem
    autocomplete_fields = ['alimento']
    extra = 1


class RefeicaoPersonalizadaAdmin(admin.ModelAdmin):
    list_display = ['nome_refeicao', 'usuario']
    list_filter = ['usuario']
    inlines = [RefeicaoPersonalizadaItemInline]

admin.site.register(RefeicaoPersonalizada, RefeicaoPersonalizadaAdmin)


class DiarioConsumoAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'data_referencia', 'total_agua_consumida_ml', 'status_dieta_cumprida']
    ordering = ['-data_referencia']
    list_filter = ['usuario', 'status_dieta_cumprida']

admin.site.register(DiarioConsumo, DiarioConsumoAdmin)


class RegistroRefeicaoItemInline(admin.TabularInline):
    model = RegistroRefeicaoItem
    autocomplete_fields = ['alimento', 'medida_caseira']
    extra = 1


class RegistroRefeicaoAdmin(admin.ModelAdmin):
    list_display = ['diario', 'tipo_refeicao', 'horario', 'refeicao_personalizada']
    ordering = ['-horario']
    list_filter = ['tipo_refeicao', 'diario__usuario']
    inlines = [RegistroRefeicaoItemInline]

admin.site.register(RegistroRefeicao, RegistroRefeicaoAdmin)


# ----- Treino e atividades -----

class ExercicioFichaInline(admin.TabularInline):
    model = ExercicioFicha
    extra = 1


class FichaTreinoAdmin(admin.ModelAdmin):
    list_display = ['nome_ficha', 'usuario', 'dias_semana', 'ativa']
    list_filter = ['usuario', 'ativa']
    inlines = [ExercicioFichaInline]

admin.site.register(FichaTreino, FichaTreinoAdmin)


class SerieExecutadaInline(admin.TabularInline):
    model = SerieExecutada
    extra = 1


class SessaoAtividadeAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'esporte', 'inicio', 'duracao_minutos', 'intensidade', 'distancia_km']
    ordering = ['-inicio']
    list_filter = ['usuario', 'esporte', 'intensidade']
    inlines = [SerieExecutadaInline]

admin.site.register(SessaoAtividade, SessaoAtividadeAdmin)


class SerieExecutadaAdmin(admin.ModelAdmin):
    list_display = ['exercicio', 'sessao', 'numero_serie', 'carga_kg', 'repeticoes']
    list_filter = ['exercicio__ficha']

admin.site.register(SerieExecutada, SerieExecutadaAdmin)


# ----- Gamificação social -----

class PerfilGamificacaoAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'streak_atual', 'pontos_experiencia', 'escudos_descanso', 'ultimo_dia_ativo']
    ordering = ['-pontos_experiencia']

admin.site.register(PerfilGamificacao, PerfilGamificacaoAdmin)


class RegistroXPAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'acao', 'pontos', 'data_referencia', 'criado_em']
    ordering = ['-data_referencia', '-criado_em']
    list_filter = ['acao', 'usuario']

admin.site.register(RegistroXP, RegistroXPAdmin)


class AmizadeAdmin(admin.ModelAdmin):
    list_display = ['usuario_1', 'usuario_2']

admin.site.register(Amizade, AmizadeAdmin)


class MembroGrupoInline(admin.TabularInline):
    model = MembroGrupo
    extra = 1


class GrupoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'criador', 'codigo_convite', 'data_criacao']
    search_fields = ['nome', 'codigo_convite']
    inlines = [MembroGrupoInline]

admin.site.register(Grupo, GrupoAdmin)


class ParticipanteDesafioInline(admin.TabularInline):
    model = ParticipanteDesafio
    extra = 1


class DesafioAdmin(admin.ModelAdmin):
    list_display = ['nome', 'grupo', 'metrica', 'data_inicio', 'data_fim']
    ordering = ['-data_inicio']
    list_filter = ['grupo', 'metrica']
    inlines = [ParticipanteDesafioInline]

admin.site.register(Desafio, DesafioAdmin)
