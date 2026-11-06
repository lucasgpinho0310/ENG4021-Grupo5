from django.urls import path

from . import views

app_name = 'evolucao'  # links: {% url 'evolucao:...' %}

urlpatterns = [
    path('', views.peso, name='peso'),
    path('<uuid:medida_id>/excluir/', views.excluir, name='excluir'),
]
