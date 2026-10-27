from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import DiarioBemEstar, RegistroDor


def criar_usuario(nome="teste@exemplo.com"):
    """Único ponto a adaptar se o modelo de usuário do projeto exigir outros campos."""
    User = get_user_model()
    return User.objects.create_user(**{User.USERNAME_FIELD: nome}, password="senha12345")


class ModeloTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.hoje = timezone.localdate()

    def test_um_diario_por_usuario_por_dia(self):
        DiarioBemEstar.objects.create(usuario=self.usuario, data_referencia=self.hoje)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DiarioBemEstar.objects.create(usuario=self.usuario, data_referencia=self.hoje)

    def test_limites_do_sono(self):
        diario = DiarioBemEstar(usuario=self.usuario, data_referencia=self.hoje, horas_sono=25)
        with self.assertRaises(ValidationError):
            diario.full_clean()
        diario.horas_sono = 7.5
        diario.qualidade_sono = 6
        with self.assertRaises(ValidationError):
            diario.full_clean()
        diario.qualidade_sono = 5
        diario.full_clean()  # agora é válido

    def test_limite_da_dor(self):
        diario = DiarioBemEstar.objects.create(usuario=self.usuario, data_referencia=self.hoje)
        dor = RegistroDor(diario=diario, regiao="joelho", intensidade=11)
        with self.assertRaises(ValidationError):
            dor.full_clean()

    def test_uma_dor_por_regiao_no_dia(self):
        diario = DiarioBemEstar.objects.create(usuario=self.usuario, data_referencia=self.hoje)
        RegistroDor.objects.create(diario=diario, regiao="joelho", intensidade=4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistroDor.objects.create(diario=diario, regiao="joelho", intensidade=7)


class ViewTest(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.url = reverse("bem_estar:registro")
        self.hoje = timezone.localdate()

    def dados(self, **extra):
        base = {
            "humor": "4", "horas_sono": "7.5", "qualidade_sono": "4", "observacao": "",
            "dores-TOTAL_FORMS": "1", "dores-INITIAL_FORMS": "0",
            "dores-MIN_NUM_FORMS": "0", "dores-MAX_NUM_FORMS": "1000",
            "dores-0-regiao": "joelho", "dores-0-intensidade": "6", "dores-0-observacao": "",
        }
        base.update(extra)
        return base

    def test_exige_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_salva_e_depois_atualiza_sem_duplicar(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(DiarioBemEstar.objects.count(), 1)
        self.assertEqual(DiarioBemEstar.objects.get().dores.count(), 1)

        # segundo envio no mesmo dia atualiza o mesmo registro (sem novas dores)
        self.client.post(self.url, self.dados(humor="2", **{"dores-TOTAL_FORMS": "0"}))
        self.assertEqual(DiarioBemEstar.objects.count(), 1)
        self.assertEqual(DiarioBemEstar.objects.get().humor, 2)

    def test_sono_invalido_nao_salva(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, self.dados(horas_sono="30"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(DiarioBemEstar.objects.count(), 0)

    def test_dia_futuro_vira_hoje(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"data": "2999-01-01"})
        self.assertEqual(resposta.context["dia"], self.hoje)

    def test_historico_mostra_so_do_proprio_usuario(self):
        outro = criar_usuario("outro@exemplo.com")
        DiarioBemEstar.objects.create(usuario=outro, data_referencia=self.hoje, observacao="segredo do outro")
        DiarioBemEstar.objects.create(usuario=self.usuario, data_referencia=self.hoje, observacao="meu registro")
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("bem_estar:historico"))
        self.assertContains(resposta, "meu registro")
        self.assertNotContains(resposta, "segredo do outro")