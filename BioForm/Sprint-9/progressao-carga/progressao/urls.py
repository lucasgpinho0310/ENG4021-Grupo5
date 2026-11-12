from django.urls import path

from . import views

app_name = 'progressao'  # links: {% url 'progressao:...' %}

urlpatterns = [
    path('<uuid:exercicio_id>/', views.exercicio, name='exercicio'),
]
