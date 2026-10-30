from decimal import Decimal

from django import forms

from saude.models import DIAS_DA_SEMANA, ExercicioFicha

from .leitor import ExercicioLido, ler_intervalo

DIAS = [(dia, nome[:3]) for dia, nome in DIAS_DA_SEMANA.items()]
IMAGEM_MAXIMA_MB = 5
TEXTO_MAXIMO = 20000
MEDIDAS = [('repeticoes', 'Repetições'), ('tempo', 'Tempo')]
LINHAS_INICIAIS = 4
LINHAS_MAXIMAS = 60


class FichaForm(forms.Form):
    """Nome, dias e situação da série. Os exercícios vêm do texto colado ou das linhas (um por um)."""
    nome = forms.CharField(
        label='Nome da série', max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Ex.: Inferiores, Treino A, Peito e tríceps'}),
    )
    dias = forms.MultipleChoiceField(
        label='Dias da semana', choices=DIAS, required=False, widget=forms.CheckboxSelectMultiple,
    )
    ativa = forms.BooleanField(label='Série ativa', required=False, initial=True)
    texto = forms.CharField(
        label='Cole os exercícios', required=False, max_length=TEXTO_MAXIMO,
        widget=forms.Textarea(attrs={
            'rows': 12,
            'placeholder': 'Cadeira Extensora\nSéries: 3x15\nCarga: 20kg\nIntervalo: 60s\n\nPrancha\nSéries: 3x30s\n...',
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


def sem_zeros(valor):
    """Decimal('100.00') -> Decimal('100'); Decimal('12.50') -> Decimal('12.5') (sem virar 1E+2)."""
    valor = Decimal(valor)
    return valor.quantize(Decimal(1)) if valor == valor.to_integral() else valor.normalize()


def _segundos(texto, erro):
    """'45' ou '45s' -> 45; '2min' -> 120; vazio -> None."""
    texto = (texto or '').strip()
    if not texto:
        return None
    segundos = ler_intervalo(texto + 's' if texto.isdigit() else texto)
    if segundos is None:
        raise forms.ValidationError(erro)
    return segundos


class CamposDeSeries(forms.Form):
    """
    Séries, repetições ou tempo, e intervalo, em campos separados.
    Exercício por tempo (prancha, isometria, estabilidade) usa "Tempo" no lugar das repetições.
    """
    series = forms.IntegerField(
        label='Séries', min_value=1, max_value=20, initial=3,
        widget=forms.NumberInput(attrs={'min': 1, 'max': 20, 'inputmode': 'numeric'}),
    )
    medida = forms.ChoiceField(label='Por', choices=MEDIDAS, initial='repeticoes')
    repeticoes = forms.IntegerField(
        label='Repetições', min_value=1, max_value=200, required=False, initial=10,
        widget=forms.NumberInput(attrs={'min': 1, 'max': 200, 'inputmode': 'numeric'}),
    )
    tempo = forms.CharField(
        label='Tempo', max_length=20, required=False,
        widget=forms.TextInput(attrs={'placeholder': '30s'}),
    )
    intervalo = forms.CharField(
        label='Intervalo', max_length=20, required=False,
        widget=forms.TextInput(attrs={'placeholder': '60s'}),
    )

    def clean_tempo(self):
        return _segundos(self.cleaned_data.get('tempo'), 'Use segundos (30s) ou minutos (1min, 1:30).')

    def clean_intervalo(self):
        return _segundos(self.cleaned_data.get('intervalo'), 'Use segundos (60s) ou minutos (2min), até 30 minutos.')

    def validar_series(self, dados):
        """Repetições obrigatórias no exercício por repetições; tempo, no exercício por tempo."""
        if dados.get('medida') == 'tempo':
            if not dados.get('tempo') and 'tempo' not in self.errors:
                self.add_error('tempo', 'Informe o tempo de cada série (ex.: 30s).')
        elif not dados.get('repeticoes') and 'repeticoes' not in self.errors:
            self.add_error('repeticoes', 'Informe as repetições.')


class LinhaExercicioForm(CamposDeSeries):
    """Uma linha da montagem "um por um" na nova série. Linha sem nome é ignorada."""
    nome = forms.CharField(
        label='Exercício', max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ex.: Cadeira extensora'}),
    )
    carga = forms.DecimalField(
        label='Carga (kg)', min_value=0, max_value=1000, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'step': '0.5', 'min': '0', 'placeholder': '0'}),
    )
    cada_lado = forms.BooleanField(label='Cada lado', required=False)

    field_order = ['nome', 'series', 'medida', 'repeticoes', 'tempo', 'carga', 'intervalo', 'cada_lado']

    def clean(self):
        dados = super().clean()
        dados['nome'] = ' '.join((dados.get('nome') or '').split())
        if dados['nome']:
            self.validar_series(dados)
        return dados

    def exercicio(self):
        """A linha preenchida como ExercicioLido, o mesmo formato do texto colado."""
        dados = self.cleaned_data
        por_tempo = dados['medida'] == 'tempo'
        return ExercicioLido(
            nome=dados['nome'],
            series=dados['series'],
            repeticoes=10 if por_tempo else dados['repeticoes'],
            tempo_segundos=dados['tempo'] if por_tempo else None,
            carga_kg=dados.get('carga') or Decimal('0'),
            intervalo_segundos=dados.get('intervalo'),
            cada_lado=dados.get('cada_lado', False),
        )


class BaseLinhas(forms.BaseFormSet):
    def exercicios(self):
        return [f.exercicio() for f in self.forms if f.cleaned_data.get('nome')]


LinhasFormSet = forms.formset_factory(
    LinhaExercicioForm, formset=BaseLinhas, extra=LINHAS_INICIAIS,
    max_num=LINHAS_MAXIMAS, absolute_max=LINHAS_MAXIMAS, validate_max=True,
)


class ExercicioForm(forms.ModelForm, CamposDeSeries):
    """Um exercício completo: séries, repetições ou tempo, carga, intervalo, instruções, imagem e vídeo."""
    remover_imagem = forms.BooleanField(label='Remover a imagem', required=False)

    class Meta:
        model = ExercicioFicha
        fields = ['nome_exercicio', 'carga_kg', 'cada_lado', 'instrucoes', 'combinado_com_anterior', 'imagem', 'video_url']
        labels = {
            'nome_exercicio': 'Exercício',
            'carga_kg': 'Carga (kg)',
            'cada_lado': 'Cada lado (exercício unilateral)',
            'instrucoes': 'Instruções',
            'combinado_com_anterior': 'Combinado com o exercício de cima (alternar, como bi-set)',
            'imagem': 'Imagem',
            'video_url': 'Link do vídeo',
        }
        widgets = {
            'nome_exercicio': forms.TextInput(attrs={'placeholder': 'Ex.: Cadeira extensora'}),
            'carga_kg': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
            'instrucoes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ex.: última série até a falha'}),
            'video_url': forms.URLInput(attrs={'placeholder': 'https://youtube.com/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['imagem'].widget = forms.FileInput(attrs={'accept': 'image/*'})
        self.fields['nome_exercicio'].required = True
        exercicio = self.instance
        if not exercicio._state.adding:  # o id (UUID) já existe antes de salvar
            self.initial.update({
                'series': exercicio.series_planejadas,
                'medida': 'tempo' if exercicio.tempo_segundos else 'repeticoes',
                'repeticoes': exercicio.repeticoes_planejadas,
                'tempo': '%ds' % exercicio.tempo_segundos if exercicio.tempo_segundos else '',
                'intervalo': '%ds' % exercicio.intervalo_segundos if exercicio.intervalo_segundos else '',
                'carga_kg': sem_zeros(exercicio.carga_kg),
            })
        else:
            self.initial.setdefault('carga_kg', Decimal('0'))

    def clean(self):
        dados = super().clean()
        self.validar_series(dados)
        return dados

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
        dados = self.cleaned_data
        exercicio.series_planejadas = dados['series']
        if dados['medida'] == 'tempo':
            exercicio.tempo_segundos = dados['tempo']
        else:
            exercicio.tempo_segundos = None
            exercicio.repeticoes_planejadas = dados['repeticoes']
        # O texto original da ficha (ex.: 3x10+10) só vale enquanto séries e repetições não mudam
        if {'series', 'medida', 'repeticoes', 'tempo'} & set(self.changed_data):
            exercicio.series_texto = ''
        exercicio.intervalo_segundos = dados['intervalo']
        # Troca ou remoção da imagem: apaga o arquivo antigo (pelo nome, para não mexer no novo)
        antiga = self.initial.get('imagem')
        nome_antigo = antiga.name if antiga else ''
        nova = 'imagem' in self.changed_data and dados.get('imagem')
        if nome_antigo and (nova or dados.get('remover_imagem')):
            exercicio.imagem.storage.delete(nome_antigo)
            if not nova:
                exercicio.imagem = ''
        if commit:
            exercicio.save()
        return exercicio
