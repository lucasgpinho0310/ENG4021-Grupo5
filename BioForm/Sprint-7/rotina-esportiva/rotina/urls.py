from django.urls import path

from . import views

urlpatterns = [
    path('rotina/', views.semana, name='rotina_semana'),
    path('rotina/confirmar/', views.confirmar, name='rotina_confirmar'),
]
