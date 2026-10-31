from django.urls import path

from . import views

app_name = 'rotina'  # links: {% url 'rotina:...' %}

urlpatterns = [
    path('', views.semana, name='rotina_semana'),
    path('confirmar/', views.confirmar, name='rotina_confirmar'),
]
