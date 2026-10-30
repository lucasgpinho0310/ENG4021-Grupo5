from django.urls import path

from . import views

app_name = 'treinos'  # links: {% url 'treinos:...' %}

urlpatterns = [
    path('', views.lista, name='treinos_lista'),
    path('nova/', views.nova, name='treinos_nova'),
    path('<uuid:ficha_id>/', views.ficha, name='treinos_ficha'),
    path('<uuid:ficha_id>/editar/', views.editar_ficha, name='treinos_editar_ficha'),
    path('<uuid:ficha_id>/ativa/', views.alternar_ativa, name='treinos_alternar_ativa'),
    path('<uuid:ficha_id>/excluir/', views.excluir_ficha, name='treinos_excluir_ficha'),
    path('<uuid:ficha_id>/colar/', views.colar, name='treinos_colar'),
    path('<uuid:ficha_id>/exercicio/novo/', views.novo_exercicio, name='treinos_novo_exercicio'),
    path('exercicio/<uuid:exercicio_id>/', views.editar_exercicio, name='treinos_editar_exercicio'),
    path('exercicio/<uuid:exercicio_id>/excluir/', views.excluir_exercicio, name='treinos_excluir_exercicio'),
    path('exercicio/<uuid:exercicio_id>/mover/', views.mover_exercicio, name='treinos_mover_exercicio'),
]
