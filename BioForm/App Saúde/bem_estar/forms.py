from django import forms
from django.forms import inlineformset_factory

from .models import DiarioBemEstar, RegistroDor


class DiarioBemEstarForm(forms.ModelForm):
    class Meta:
        model = DiarioBemEstar
        fields = ["humor", "horas_sono", "qualidade_sono", "observacao"]
        widgets = {
            "horas_sono": forms.NumberInput(attrs={"step": "0.25", "min": "0", "max": "24"}),
            "qualidade_sono": forms.NumberInput(attrs={"min": "1", "max": "5"}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }


# Prefixo fixo "dores": os campos do formulário se chamam dores-0-regiao, dores-0-intensidade...
DorFormSet = inlineformset_factory(
    DiarioBemEstar,
    RegistroDor,
    fields=["regiao", "intensidade", "observacao"],
    extra=2,
    can_delete=True,
    widgets={"intensidade": forms.NumberInput(attrs={"min": "0", "max": "10"})},
)