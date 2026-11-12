from django import forms


class AdicionarAmigoForm(forms.Form):
    email = forms.EmailField(
        label='E-mail do amigo',
        widget=forms.EmailInput(attrs={'placeholder': 'amigo@email.com', 'autocomplete': 'off'}),
    )
