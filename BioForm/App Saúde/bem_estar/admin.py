from django.contrib import admin

from .models import DiarioBemEstar, RegistroDor


class RegistroDorInline(admin.TabularInline):
    model = RegistroDor
    extra = 0


@admin.register(DiarioBemEstar)
class DiarioBemEstarAdmin(admin.ModelAdmin):
    list_display = ("usuario", "data_referencia", "humor", "horas_sono", "qualidade_sono")
    list_filter = ("humor",)
    date_hierarchy = "data_referencia"
    inlines = [RegistroDorInline]