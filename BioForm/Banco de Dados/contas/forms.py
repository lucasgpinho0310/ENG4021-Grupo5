"""
Formulários das telas de conta e perfil.

A validação do navegador (HTML5) é só conforto: tudo é validado de novo aqui no servidor.
"""
import re
from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from rotina import campos as campos_rotina
from saude.models import INTENSIDADES, OBJETIVOS, Esporte, Usuario
from .templatetags.bioform import celular_formatado

User = get_user_model()

IDADE_MINIMA = 14
IDADE_MAXIMA = 100


def so_digitos(texto):
    return re.sub(r'\D', '', texto or '')


def cpf_valido(cpf):
    """Confere os dois dígitos verificadores do CPF (11 números, sem pontuação)."""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(cpf[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = soma * 10 % 11 % 10
        if digito != int(cpf[posicao]):
            return False
    return True


# =====================================================================
# Conta: cadastro, login e edição
# =====================================================================

class CadastroForm(forms.Form):
    nome_completo = forms.CharField(
        label='Nome completo', min_length=3, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Seu nome e sobrenome', 'autocomplete': 'name', 'minlength': 3}),
    )
    cpf = forms.CharField(
        label='CPF', max_length=14,
        widget=forms.TextInput(attrs={
            'placeholder': '000.000.000-00', 'inputmode': 'numeric', 'maxlength': 14,
            'pattern': r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', 'title': 'Digite os 11 números do CPF',
        }),
    )
    celular = forms.CharField(
        label='Celular', max_length=15,
        widget=forms.TextInput(attrs={
            'type': 'tel', 'placeholder': '(21) 99999-9999', 'autocomplete': 'tel', 'maxlength': 15,
            'pattern': r'\(?\d{2}\)?\s?9?\d{4}-?\d{4}', 'title': 'Digite o DDD e o número',
        }),
    )
    email = forms.EmailField(
        label='E-mail', max_length=150,
        widget=forms.EmailInput(attrs={'placeholder': 'voce@email.com', 'autocomplete': 'email'}),
    )
    senha = forms.CharField(
        label='Senha', strip=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Crie uma senha', 'autocomplete': 'new-password', 'minlength': 8}),
    )
    confirmar = forms.CharField(
        label='Confirmar senha', strip=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Repita a senha', 'autocomplete': 'new-password', 'minlength': 8}),
    )
    aceitou_termos = forms.BooleanField(
        error_messages={'required': 'É preciso aceitar os Termos de Uso e a Política de Privacidade.'},
    )

    def clean_cpf(self):
        cpf = so_digitos(self.cleaned_data['cpf'])
        if not cpf_valido(cpf):
            raise forms.ValidationError('CPF inválido. Confira os números.')
        if Usuario.objects.filter(cpf=cpf).exists():
            raise forms.ValidationError('Já existe uma conta com este CPF.')
        return cpf

    def clean_celular(self):
        celular = so_digitos(self.cleaned_data['celular'])
        if len(celular) not in (10, 11):
            raise forms.ValidationError('Digite o DDD e o número do celular.')
        return celular

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email

    def clean(self):
        dados = super().clean()
        senha, confirmar = dados.get('senha'), dados.get('confirmar')
        if senha and confirmar and senha != confirmar:
            self.add_error('confirmar', 'As senhas precisam ser iguais.')
        elif senha:
            provisorio = User(username=dados.get('email', ''), email=dados.get('email', ''),
                              first_name=dados.get('nome_completo', ''))
            try:
                validate_password(senha, provisorio)
            except forms.ValidationError as erro:
                self.add_error('senha', erro)
        return dados

    @transaction.atomic
    def save(self):
        dados = self.cleaned_data
        conta = User.objects.create_user(
            username=dados['email'],  # o login é pelo e-mail ou CPF; o username só guarda o e-mail
            email=dados['email'],
            password=dados['senha'],
            first_name=dados['nome_completo'].split()[0][:150],
        )
        Usuario.objects.create(
            conta=conta,
            nome_completo=dados['nome_completo'],
            cpf=dados['cpf'],
            celular=dados['celular'],
            aceitou_termos=True,
        )
        return conta


class EntrarForm(AuthenticationForm):
    username = forms.CharField(
        label='E-mail ou CPF', max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'voce@email.com', 'autocomplete': 'username', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Senha', strip=False,
        widget=forms.PasswordInput(attrs={'placeholder': 'Digite sua senha', 'autocomplete': 'current-password'}),
    )
    lembrar = forms.BooleanField(label='Lembrar de mim', required=False)

    error_messages = {
        'invalid_login': 'E-mail/CPF ou senha incorretos.',
        'inactive': 'Esta conta está desativada.',
    }


class ContaForm(forms.ModelForm):
    """Editar perfil: dados da conta (o CPF não muda)."""
    email = forms.EmailField(label='E-mail', max_length=150)

    class Meta:
        model = Usuario
        fields = ['nome_completo', 'apelido', 'celular']
        labels = {'nome_completo': 'Nome completo', 'apelido': 'Como quer ser chamado?', 'celular': 'Celular'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].initial = self.instance.conta.email
        self.initial['celular'] = celular_formatado(self.instance.celular)
        self.fields['nome_completo'].min_length = 3
        self.order_fields(['nome_completo', 'apelido', 'email', 'celular'])
        for nome, campo in self.fields.items():
            campo.widget.attrs['class'] = 'input'

    def clean_celular(self):
        celular = so_digitos(self.cleaned_data['celular'])
        if len(celular) not in (10, 11):
            raise forms.ValidationError('Digite o DDD e o número do celular.')
        return celular

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        outros = User.objects.exclude(pk=self.instance.conta.pk)
        if outros.filter(email__iexact=email).exists() or outros.filter(username__iexact=email).exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email

    @transaction.atomic
    def save(self):
        usuario = super().save()
        conta = usuario.conta
        conta.email = conta.username = self.cleaned_data['email']
        conta.first_name = usuario.nome_completo.split()[0][:150]
        conta.save()
        return usuario


class ExcluirContaForm(forms.Form):
    senha = forms.CharField(
        label='Digite sua senha para confirmar', strip=False,
        widget=forms.PasswordInput(attrs={'class': 'input', 'autocomplete': 'current-password'}),
    )

    def __init__(self, conta, *args, **kwargs):
        self.conta = conta
        super().__init__(*args, **kwargs)

    def clean_senha(self):
        if not self.conta.check_password(self.cleaned_data['senha']):
            raise forms.ValidationError('Senha incorreta.')
        return self.cleaned_data['senha']


# =====================================================================
# Onboarding do perfil (passos 1 a 3)
# =====================================================================

class DadosForm(forms.ModelForm):
    """Passo 1: sobre você, sexo biológico e medidas."""
    peso_kg = forms.DecimalField(
        label='Peso atual', min_value=30, max_value=300, decimal_places=1, max_digits=5,
        widget=forms.NumberInput(attrs={'placeholder': '78,5', 'step': '0.1', 'inputmode': 'decimal'}),
    )

    class Meta:
        model = Usuario
        fields = ['apelido', 'data_nascimento', 'sexo_biologico', 'altura_cm', 'peso_meta_kg']
        labels = {
            'apelido': 'Como quer ser chamado?',
            'data_nascimento': 'Data de nascimento',
            'altura_cm': 'Altura',
            'peso_meta_kg': 'Peso desejado (opcional)',
        }
        widgets = {
            'apelido': forms.TextInput(attrs={'placeholder': 'Ex.: Edson'}),
            'data_nascimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'min': '1920-01-01'}),
            'altura_cm': forms.NumberInput(attrs={'placeholder': '178', 'min': 100, 'max': 250, 'inputmode': 'numeric'}),
            'peso_meta_kg': forms.NumberInput(attrs={'placeholder': '74', 'min': 30, 'max': 300, 'step': '0.1', 'inputmode': 'decimal'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ('apelido', 'data_nascimento', 'sexo_biologico', 'altura_cm'):
            self.fields[campo].required = True
        self.fields['sexo_biologico'].choices = [c for c in self.fields['sexo_biologico'].choices if c[0]]
        hoje = timezone.localdate()
        limite = date(hoje.year - IDADE_MINIMA, hoje.month, min(hoje.day, 28))  # dica para o calendário do navegador
        self.fields['data_nascimento'].widget.attrs['max'] = limite.isoformat()

    def clean_apelido(self):
        apelido = self.cleaned_data['apelido'].strip()
        if not apelido:
            raise forms.ValidationError('Diga como quer ser chamado.')
        return apelido

    def clean_data_nascimento(self):
        nascimento = self.cleaned_data['data_nascimento']
        hoje = timezone.localdate()
        idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        if idade < IDADE_MINIMA:
            raise forms.ValidationError('O BioForm é para maiores de %d anos.' % IDADE_MINIMA)
        if idade > IDADE_MAXIMA or nascimento < date(1900, 1, 1):
            raise forms.ValidationError('Confira a data de nascimento.')
        return nascimento

    def clean_peso_meta_kg(self):
        peso_meta = self.cleaned_data.get('peso_meta_kg')
        if peso_meta is not None and not 30 <= peso_meta <= 300:  # o modelo não tem esse limite
            raise forms.ValidationError('O peso desejado deve estar entre 30 e 300 kg.')
        return peso_meta


class ObjetivoForm(forms.ModelForm):
    """Passo 2: biotipo e objetivo principal."""
    objetivo = forms.ChoiceField(choices=OBJETIVOS.items())

    class Meta:
        model = Usuario
        fields = ['biotipo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['biotipo'].required = True
        self.fields['biotipo'].choices = [c for c in self.fields['biotipo'].choices if c[0]]


# Ícone e nome de exibição dos esportes do catálogo (o resto usa o nome do banco)
APARENCIA_ESPORTES = {
    'musculacao': ('🏋️', 'Musculação'),
    'corrida': ('🏃', 'Corrida'),
    'ciclismo': ('🚴', 'Ciclismo'),
    'natacao': ('🏊', 'Natação'),
    'funcional': ('🔥', 'Funcional / Crossfit'),
    'futebol': ('⚽', 'Futebol'),
    'lutas': ('🥊', 'Lutas'),
    'yoga': ('🧘', 'Yoga / Pilates'),
    'volei': ('🏐', 'Vôlei'),
    'futevolei': ('🏖️', 'Futevôlei'),
}

FREQUENCIAS = [(str(n), '%dx' % n) for n in range(1, 7)] + [('7', 'Diário')]


class EsportesForm(forms.Form):
    """
    Passo 3: um grupo de campos por esporte do catálogo:
    pratica_<slug> (marcou?), freq_<slug> (vezes por semana) e int_<slug> (intensidade),
    mais a duração e os dias fixos (dur_<slug>, fixos_<slug>, dias_<slug>, em rotina/campos.py).
    """

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        atuais = {}
        if usuario is not None:
            atuais = {e.esporte_id: e for e in usuario.esportes.all()}
        self.esportes = []
        for esporte in Esporte.objects.all():
            slug = slugify(esporte.nome)
            atual = atuais.get(esporte.id)
            self.fields['pratica_' + slug] = forms.BooleanField(required=False, initial=atual is not None)
            self.fields['freq_' + slug] = forms.ChoiceField(
                choices=FREQUENCIAS, required=False,
                initial=str(atual.frequencia_semanal) if atual else '3',
            )
            self.fields['int_' + slug] = forms.ChoiceField(
                choices=INTENSIDADES.items(), required=False,
                initial=atual.intensidade if atual else 'moderada',
            )
            campos_rotina.adicionar_campos(self, slug, atual)
            emoji, nome = APARENCIA_ESPORTES.get(slug, ('🏅', esporte.nome))
            self.esportes.append({'esporte': esporte, 'slug': slug, 'emoji': emoji, 'nome': nome})

    def clean(self):
        dados = super().clean()
        for item in self.esportes:
            slug = item['slug']
            if dados.get('pratica_' + slug) and not (dados.get('freq_' + slug) and dados.get('int_' + slug)):
                raise forms.ValidationError('Escolha a frequência e a intensidade de %s.' % item['nome'])
            if dados.get('pratica_' + slug):
                erro = campos_rotina.validar(dados, slug, item['nome'])
                if erro:
                    raise forms.ValidationError(erro)
        return dados

    def escolhidos(self):
        """Lista de (esporte, vezes por semana, intensidade, minutos, dias fixos) dos esportes marcados."""
        return [
            (
                item['esporte'],
                int(self.cleaned_data['freq_' + item['slug']]),
                self.cleaned_data['int_' + item['slug']],
                *campos_rotina.valores(self.cleaned_data, item['slug']),
            )
            for item in self.esportes
            if self.cleaned_data.get('pratica_' + item['slug'])
        ]

    def grupos(self):
        """Dados prontos para o template montar os chips de cada esporte."""
        for item in self.esportes:
            slug = item['slug']
            yield {
                **item,
                'marcado': self['pratica_' + slug].value(),
                'freq_nome': self['freq_' + slug].html_name,
                'freq_valor': str(self['freq_' + slug].value()),
                'int_nome': self['int_' + slug].html_name,
                'int_valor': self['int_' + slug].value(),
                'pratica_nome': self['pratica_' + slug].html_name,
                **campos_rotina.contexto(self, slug),
            }
