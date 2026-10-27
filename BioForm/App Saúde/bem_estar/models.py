"""Diário de bem-estar: humor, sono e dores. Tabelas: diario_bem_estar e registros_dor."""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class DiarioBemEstar(models.Model):
    """Um registro por usuário por dia: humor e sono. As dores ficam em tabela própria."""

    class Humor(models.IntegerChoices):
        MUITO_RUIM = 1, "Muito ruim"
        RUIM = 2, "Ruim"
        NEUTRO = 3, "Neutro"
        BOM = 4, "Bom"
        MUITO_BOM = 5, "Muito bom"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="diarios_bem_estar"
    )
    data_referencia = models.DateField()
    humor = models.PositiveSmallIntegerField(choices=Humor.choices, null=True, blank=True)
    horas_sono = models.DecimalField(
        "horas de sono", max_digits=4, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    qualidade_sono = models.PositiveSmallIntegerField(
        "qualidade do sono (1 a 5)", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    observacao = models.TextField("observação", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "diario_bem_estar"
        ordering = ["-data_referencia"]
        verbose_name = "diário de bem-estar"
        verbose_name_plural = "diários de bem-estar"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "data_referencia"], name="um_diario_bem_estar_por_dia"
            ),
            models.CheckConstraint(
                condition=Q(horas_sono__isnull=True) | (Q(horas_sono__gte=0) & Q(horas_sono__lte=24)),
                name="horas_sono_entre_0_e_24",
            ),
            models.CheckConstraint(
                condition=Q(qualidade_sono__isnull=True)
                | (Q(qualidade_sono__gte=1) & Q(qualidade_sono__lte=5)),
                name="qualidade_sono_entre_1_e_5",
            ),
        ]

    def __str__(self):
        return f"Bem-estar de {self.usuario_id} em {self.data_referencia}"


class RegistroDor(models.Model):
    """Uma dor por região do corpo em um dia. Tabela própria porque um dia pode ter várias dores."""

    class Regiao(models.TextChoices):
        CABECA = "cabeca", "Cabeça"
        PESCOCO = "pescoco", "Pescoço"
        OMBRO = "ombro", "Ombro"
        COSTAS = "costas", "Costas"
        PEITO = "peito", "Peito"
        BRACO = "braco", "Braço"
        PUNHO = "punho", "Punho"
        QUADRIL = "quadril", "Quadril"
        COXA = "coxa", "Coxa"
        JOELHO = "joelho", "Joelho"
        PANTURRILHA = "panturrilha", "Panturrilha"
        TORNOZELO = "tornozelo", "Tornozelo"
        OUTRA = "outra", "Outra"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    diario = models.ForeignKey(DiarioBemEstar, on_delete=models.CASCADE, related_name="dores")
    regiao = models.CharField("região", max_length=20, choices=Regiao.choices)
    intensidade = models.PositiveSmallIntegerField(
        "intensidade (0 a 10)", validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    observacao = models.CharField("observação", max_length=255, blank=True)

    class Meta:
        db_table = "registros_dor"
        verbose_name = "dor"
        verbose_name_plural = "dores"
        constraints = [
            models.UniqueConstraint(fields=["diario", "regiao"], name="uma_dor_por_regiao_por_dia"),
            models.CheckConstraint(
                condition=Q(intensidade__gte=0) & Q(intensidade__lte=10),
                name="intensidade_dor_entre_0_e_10",
            ),
        ]

    def __str__(self):
        return f"{self.get_regiao_display()} ({self.intensidade}/10)"