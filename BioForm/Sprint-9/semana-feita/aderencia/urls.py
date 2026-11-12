from django.urls import path

from . import views

app_name = 'aderencia'  # links: {% url 'aderencia:...' %}

urlpatterns = [
    path('', views.semana, name='semana'),
]
