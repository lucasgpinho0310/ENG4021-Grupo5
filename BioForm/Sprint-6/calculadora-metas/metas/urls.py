from django.urls import path

from . import views

app_name = 'metas'  # links: {% url 'metas:...' %}

urlpatterns = [
    path('', views.perfil_metas, name='perfil_metas'),
]
