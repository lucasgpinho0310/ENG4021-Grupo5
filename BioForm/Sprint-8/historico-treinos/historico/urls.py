from django.urls import path

from . import views

app_name = 'historico'  # links: {% url 'historico:...' %}

urlpatterns = [
    path('', views.lista, name='lista'),
    path('<uuid:sessao_id>/', views.sessao, name='sessao'),
    path('<uuid:sessao_id>/excluir/', views.excluir, name='excluir'),
]
