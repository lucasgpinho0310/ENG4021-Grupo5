from django import forms
from django.utils import timezone

from saude.models import INTENSIDADES


class TreinoForm(forms.Form):
    """Dados gerais do treino feito (as séries vêm em campos próprios, uma linha por série)."""
    data = forms.DateField(label='Data', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    duracao = forms.IntegerField(label='Duração (min)', min_value=1, max_value=600)
    intensidade = forms.ChoiceField(label='Intensidade', choices=INTENSIDADES.items())

    def clean_data(self):
        data = self.cleaned_data['data']
        if data > timezone.localdate():
            raise forms.ValidationError('O treino não pode ser numa data futura.')
        return data
