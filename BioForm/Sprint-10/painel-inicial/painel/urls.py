from django.urls import path

from . import views

app_name = 'painel'

urlpatterns = [
    path('', views.hoje, name='hoje'),
]
