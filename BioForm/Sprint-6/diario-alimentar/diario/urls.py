from datetime import date

from django.urls import path, register_converter

from . import views


class DataConverter:
    """Datas no endereço no formato 2026-10-22 (data inválida vira 404)."""
    regex = r'\d{4}-\d{2}-\d{2}'

    def to_python(self, valor):
        return date.fromisoformat(valor)

    def to_url(self, valor):
        return valor.isoformat()


register_converter(DataConverter, 'data')

app_name = 'diario'  # links: {% url 'diario:...' %}

urlpatterns = [
    path('', views.dia, name='diario_hoje'),
    path('historico/', views.historico, name='diario_historico'),
    path('<data:data>/', views.dia, name='diario_dia'),
    path('<data:data>/adicionar/', views.adicionar, name='diario_adicionar'),
    path('<data:data>/agua/', views.agua, name='diario_agua'),
    path('<data:data>/checkin/', views.checkin, name='diario_checkin'),
    path('<data:data>/combo/', views.usar_combo, name='diario_usar_combo'),
    path('item/<uuid:item_id>/remover/', views.remover_item, name='diario_remover_item'),
    path('refeicao/<uuid:registro_id>/salvar-combo/', views.salvar_combo, name='diario_salvar_combo'),
    path('combo/<uuid:combo_id>/excluir/', views.excluir_combo, name='diario_excluir_combo'),
]
