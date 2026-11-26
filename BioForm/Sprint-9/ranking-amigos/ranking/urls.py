from django.urls import path

from . import views

app_name = 'ranking'  # links: {% url 'ranking:...' %}

urlpatterns = [
    path('', views.ranking, name='semana'),
    path('amigos/', views.amigos, name='amigos'),
    path('amigos/<uuid:amigo_id>/remover/', views.remover, name='remover'),
]
