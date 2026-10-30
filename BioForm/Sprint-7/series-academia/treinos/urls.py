from django.urls import path

from . import views

urlpatterns = [
    path('treinos/', views.lista, name='treinos_lista'),
    path('treinos/nova/', views.nova, name='treinos_nova'),
    path('treinos/<uuid:ficha_id>/', views.ficha, name='treinos_ficha'),
    path('treinos/<uuid:ficha_id>/editar/', views.editar_ficha, name='treinos_editar_ficha'),
    path('treinos/<uuid:ficha_id>/ativa/', views.alternar_ativa, name='treinos_alternar_ativa'),
    path('treinos/<uuid:ficha_id>/excluir/', views.excluir_ficha, name='treinos_excluir_ficha'),
    path('treinos/<uuid:ficha_id>/colar/', views.colar, name='treinos_colar'),
    path('treinos/<uuid:ficha_id>/exercicio/novo/', views.novo_exercicio, name='treinos_novo_exercicio'),
    path('treinos/exercicio/<uuid:exercicio_id>/', views.editar_exercicio, name='treinos_editar_exercicio'),
    path('treinos/exercicio/<uuid:exercicio_id>/excluir/', views.excluir_exercicio, name='treinos_excluir_exercicio'),
    path('treinos/exercicio/<uuid:exercicio_id>/mover/', views.mover_exercicio, name='treinos_mover_exercicio'),
]
