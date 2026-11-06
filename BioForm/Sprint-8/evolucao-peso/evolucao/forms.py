from datetime import date
from decimal import Decimal

from django import forms
from django.utils import timezone


class DecimalComVirgula(forms.DecimalField):
    """Aceita "72,5" (como se escreve no Brasil) além de "72.5"."""
    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip().replace(',', '.')
        return super().to_python(value)


class PesagemForm(forms.Form):
    peso = DecimalComVirgula(
        label='Peso (kg)', min_value=Decimal('30'), max_value=Decimal('300'), max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.1', 'inputmode': 'decimal', 'placeholder': 'Ex.: 72,5'}),
    )
    data = forms.DateField(label='Data', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def clean_data(self):
        data = self.cleaned_data['data']
        if data > timezone.localdate():
            raise forms.ValidationError('A pesagem não pode ser numa data futura.')
        if data < date(2000, 1, 1):
            raise forms.ValidationError('Informe uma data a partir de 2000.')
        return data
