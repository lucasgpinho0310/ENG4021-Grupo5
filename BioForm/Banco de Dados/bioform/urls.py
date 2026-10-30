"""
URL configuration for bioform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from bioform import views  # home-page
from contas.views import EntrarView, TrocarSenhaView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),

    # Login e senha no padrão do Django (rotas accounts/...).
    # As duas primeiras usam as telas do BioForm: login com e-mail ou CPF e troca de senha
    # que volta para "Editar perfil". As demais vêm de django.contrib.auth.urls.
    path('accounts/login/', EntrarView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/password_change/', TrocarSenhaView.as_view(template_name='registration/password_change_form.html'), name='password_change'),
    path('accounts/', include('django.contrib.auth.urls')),

    # Cada app tem o seu urls.py (com app_name) e o seu prefixo de rota
    path('', include('contas.urls')),             # cadastro, perfil e conta
    path('perfil/metas/', include('metas.urls')),  # Sprint-6/calculadora-metas
    path('diario/', include('diario.urls')),       # Sprint-6/diario-alimentar
    path('rotina/', include('rotina.urls')),       # Sprint-7/rotina-esportiva
    path('treinos/', include('treinos.urls')),     # Sprint-7/series-academia
]

# Em desenvolvimento, o próprio Django entrega as imagens enviadas
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
