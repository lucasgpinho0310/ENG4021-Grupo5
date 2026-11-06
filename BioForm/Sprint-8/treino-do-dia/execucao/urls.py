from django.urls import path

from . import views

app_name = 'execucao'  # links: {% url 'execucao:...' %}

urlpatterns = [
    path('<uuid:ficha_id>/', views.fazer, name='fazer'),
]
