from decimal import Decimal

from django import forms

from saude.models import DIAS_DA_SEMANA, ExercicioFicha

from .leitor import ler_intervalo, ler_series

DIAS = [(dia, nome[:3]) for dia, nome in DIAS_DA_SEMANA.items()]
IMAGEM_MAXIMA_MB = 5
TEXTO_MAXIMO = 20000


class FichaForm(forms.Form):
    """Nome, dias e situação da série. O texto colado é opcional (dá para ir exercício por exercício)."""
    nome = forms.CharField(
        label='Nome da série', max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Ex.: Inferiores, Treino A, Peito e tríceps'}),
    )
    dias = forms.MultipleChoiceField(
        label='Dias da semana', choices=DIAS, required=False, widget=forms.CheckboxSelectMultiple,
    )
    ativa = forms.BooleanField(label='Série ativa', required=False, initial=True)
    texto = forms.CharField(
        label='Cole os exercícios (opcional)', required=False, max_length=TEXTO_MAXIMO,
        widget=forms.Textarea(attrs={
            'rows': 12,
            'placeholder': 'Cadeira Extensora\nSéries: 3x15\nCarga: 20kg\nIntervalo: 60s\n\nCadeira Flexora\nSéries: 3x10\n...',
        }),
    )

    def clean_nome(self):
        nome = ' '.join(self.cleaned_data['nome'].split())
        if not nome:
            raise forms.ValidationError('Dê um nome para a série.')
        return nome


class EditarFichaForm(FichaForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['texto']


class TextoForm(forms.Form):
    """Colar mais exercícios numa série que já existe."""
    texto = forms.CharField(
        label='Cole os exercícios', max_length=TEXTO_MAXIMO,
        widget=forms.Textarea(attrs={'rows': 12, 'placeholder': 'Nome do exercício\nSéries: 3x10\nCarga: 0kg\nIntervalo: 60s'}),
    )


class ExercicioForm(forms.ModelForm):
    """Um exercício de cada vez. "Séries" é escrito como na ficha (3x10, 3/10 cada lado, 3x10+10)."""
    series = forms.CharField(
        label='Séries', max_length=60,
        widget=forms.TextInput(attrs={'placeholder': '3x10'}),
        help_text='Como na ficha: 3x10, 3/12, 4x8-10, 3x10+10.',
    )
    intervalo = forms.CharField(
        label='Intervalo', max_length=20, required=False,
        widget=forms.TextInput(attrs={'placeholder': '60s'}),
        help_text='Em segundos (60s) ou minutos (2min, 1:30).',
    )
    remover_imagem = forms.BooleanField(label='Remover a imagem', required=False)

    class Meta:
        model = ExercicioFicha
        fields = ['nome_exercicio', 'carga_kg', 'cada_lado', 'instrucoes', 'combinado_com_anterior', 'imagem', 'video_url']
        labels = {
            'nome_exercicio': 'Exercício',
            'carga_kg': 'Carga (kg)',
            'cada_lado': 'Repetições em cada lado (unilateral)',
            'instrucoes': 'Instruções',
            'combinado_com_anterior': 'Combinado com o exercício de cima (alternar, como bi-set)',
            'imagem': 'Imagem',
            'video_url': 'Link do vídeo',
        }
        widgets = {
            'nome_exercicio': forms.TextInput(attrs={'placeholder': 'Ex.: Cadeira extensora'}),
            'carga_kg': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
            'instrucoes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ex.: última série até a falha'}),
            'imagem': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'video_url': forms.URLInput(attrs={'placeholder': 'https://youtube.com/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['imagem'].widget = forms.FileInput(attrs={'accept': 'image/*'})
        self.fields['nome_exercicio'].required = True
        exercicio = self.instance
        if exercicio.pk:
            self.fields['series'].initial = exercicio.series_texto or '%dx%d' % (
                exercicio.series_planejadas, exercicio.repeticoes_planejadas)
            if exercicio.intervalo_segundos:
                self.fields['intervalo'].initial = '%ds' % exercicio.intervalo_segundos
        else:
            self.fields['series'].initial = '3x10'
            self.fields['carga_kg'].initial = Decimal('0')

    def clean_series(self):
        texto = ' '.join(self.cleaned_data['series'].split())
        lido = ler_series(texto)
        if not lido:
            raise forms.ValidationError('Escreva séries x repetições, por exemplo 3x10 ou 3/12.')
        self.series_lidas = lido
        return texto

    def clean_intervalo(self):
        texto = self.cleaned_data['intervalo'].strip()
        if not texto:
            return None
        segundos = ler_intervalo(texto)
        if segundos is None:
            raise forms.ValidationError('Use segundos (60s) ou minutos (2min), até 30 minutos.')
        return segundos

    def clean_imagem(self):
        imagem = self.cleaned_data.get('imagem')
        if imagem and hasattr(imagem, 'size') and imagem.size > IMAGEM_MAXIMA_MB * 1024 * 1024:
            raise forms.ValidationError('A imagem pode ter até %d MB.' % IMAGEM_MAXIMA_MB)
        return imagem

    def clean_carga_kg(self):
        carga = self.cleaned_data.get('carga_kg')
        return Decimal('0') if carga is None else carga

    def save(self, commit=True):
        exercicio = super().save(commit=False)
        series, repeticoes, cada_lado = self.series_lidas
        exercicio.series_planejadas = series
        exercicio.repeticoes_planejadas = repeticoes
        exercicio.series_texto = self.cleaned_data['series']
        exercicio.cada_lado = self.cleaned_data['cada_lado'] or cada_lado
        exercicio.intervalo_segundos = self.cleaned_data['intervalo']
        # Troca ou remoção da imagem: apaga o arquivo antigo (pelo nome, para não mexer no novo)
        antiga = self.initial.get('imagem')
        nome_antigo = antiga.name if antiga else ''
        nova = 'imagem' in self.changed_data and self.cleaned_data.get('imagem')
        if nome_antigo and (nova or self.cleaned_data.get('remover_imagem')):
            exercicio.imagem.storage.delete(nome_antigo)
            if not nova:
                exercicio.imagem = ''
        if commit:
            exercicio.save()
        return exercicio
