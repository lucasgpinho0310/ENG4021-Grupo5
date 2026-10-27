from django.urls import path

from . import views

app_name = "bem_estar"

urlpatterns = [
    path("", views.registro, name="registro"),
    path("historico/", views.historico, name="historico"),
]