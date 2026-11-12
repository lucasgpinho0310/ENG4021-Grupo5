from django.urls import path

from diario import urls as _diario_urls  # noqa: F401 (registra o conversor de datas <data:...>)

from . import views

app_name = 'balanco'  # links: {% url 'balanco:...' %}

urlpatterns = [
    path('', views.dia, name='hoje'),
    path('<data:data>/', views.dia, name='dia'),
]
