from datetime import datetime, timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from saude.models import DIAS_DA_SEMANA, INTENSIDADES, Esporte, ExercicioFicha

from .leitor import ExercicioLido, ler_intervalo
from .servicos import blocos_da_ficha
from .sessoes import SERIES_MAXIMAS, ExercicioLivre, SerieFeita

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


# =====================================================================
# Treino feito: o que foi feito de verdade em cada série (sessoes.py)
# =====================================================================

FORMATO_INICIO = '%Y-%m-%dT%H:%M'  # o que o <input type="datetime-local"> envia
CARGA_MAXIMA = 1000
REPETICOES_MAXIMAS = 200
TOLERANCIA_FUTURO = timedelta(minutes=5)  # relógio do celular um pouco adiantado


class TreinoFeitoForm(forms.Form):
    """
    Uma linha por série planejada de cada exercício da ficha: feita?, carga e repetições (ou tempo).
    Os campos de cada série se chamam feita-<exercício>-<n>, carga-<exercício>-<n> e
    reps-<exercício>-<n> (ou tempo-<exercício>-<n>), e já vêm com o que foi feito da última vez.
    """
    inicio = forms.DateTimeField(
        label='Começou em', input_formats=[FORMATO_INICIO],
        widget=forms.DateTimeInput(format=FORMATO_INICIO, attrs={'type': 'datetime-local'}),
    )
    duracao = forms.IntegerField(
        label='Duração (min)', min_value=1, max_value=600,
        widget=forms.NumberInput(attrs={'min': 1, 'max': 600, 'inputmode': 'numeric'}),
    )
    intensidade = forms.ChoiceField(label='Intensidade', choices=INTENSIDADES.items())

    def __init__(self, exercicios, ultimas, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exercicios = exercicios
        self.ultimas = ultimas
        self.fields['inicio'].widget.attrs['max'] = timezone.localtime().strftime(FORMATO_INICIO)
        for exercicio in exercicios:
            anteriores = {s.numero_serie: s for s in ultimas.get(exercicio.id, (None, []))[1]}
            for numero in self.numeros(exercicio):
                anterior = anteriores.get(numero)
                chave = self.chave(exercicio, numero)
                self.fields['feita-' + chave] = forms.BooleanField(required=False, initial=True)
                self.fields['carga-' + chave] = forms.DecimalField(
                    min_value=0, max_value=CARGA_MAXIMA, decimal_places=2, required=False,
                    initial=sem_zeros(anterior.carga_kg if anterior else exercicio.carga_kg),
                    widget=forms.NumberInput(attrs={'step': 'any', 'min': 0, 'inputmode': 'decimal'}),
                )
                if exercicio.tempo_segundos:
                    segundos = anterior.tempo_segundos if anterior and anterior.tempo_segundos else exercicio.tempo_segundos
                    self.fields['tempo-' + chave] = forms.CharField(
                        max_length=20, required=False, initial='%ds' % segundos,
                        widget=forms.TextInput(attrs={'placeholder': '30s'}),
                    )
                else:
                    repeticoes = anterior.repeticoes if anterior and anterior.repeticoes else exercicio.repeticoes_planejadas
                    self.fields['reps-' + chave] = forms.IntegerField(
                        min_value=1, max_value=REPETICOES_MAXIMAS, required=False, initial=repeticoes,
                        widget=forms.NumberInput(attrs={'min': 1, 'max': REPETICOES_MAXIMAS, 'inputmode': 'numeric'}),
                    )

    @staticmethod
    def chave(exercicio, numero):
        return '%s-%d' % (exercicio.id.hex, numero)

    @staticmethod
    def numeros(exercicio):
        return range(1, min(exercicio.series_planejadas, SERIES_MAXIMAS) + 1)

    def clean_inicio(self):
        inicio = self.cleaned_data['inicio']
        if inicio > timezone.now() + TOLERANCIA_FUTURO:
            raise forms.ValidationError('O treino não pode começar no futuro.')
        return inicio

    def clean(self):
        dados = super().clean()
        self.feitos = []
        for exercicio in self.exercicios:
            series = []
            for numero in self.numeros(exercicio):
                chave = self.chave(exercicio, numero)
                if not dados.get('feita-' + chave):
                    continue
                carga = dados.get('carga-' + chave)
                serie = SerieFeita(numero=numero, carga_kg=Decimal('0') if carga is None else carga)
                if exercicio.tempo_segundos:
                    campo = 'tempo-' + chave
                    if campo in self.errors:
                        continue
                    try:
                        serie.tempo_segundos = _segundos(dados.get(campo), 'Use segundos (30s) ou minutos (1min, 1:30).')
                    except forms.ValidationError as erro:
                        self.add_error(campo, erro)
                        continue
                    if not serie.tempo_segundos:
                        self.add_error(campo, 'Informe o tempo.')
                        continue
                else:
                    campo = 'reps-' + chave
                    serie.repeticoes = dados.get(campo)
                    if not serie.repeticoes:
                        if campo not in self.errors:
                            self.add_error(campo, 'Informe as repetições.')
                        continue
                series.append(serie)
            if series:
                self.feitos.append((exercicio, series))
        if not self.errors and not self.feitos:
            raise forms.ValidationError('Marque pelo menos uma série feita.')
        return dados

    def blocos(self):
        """Exercícios na ordem da ficha, juntando os combinados, com os campos de cada série."""
        for bloco in blocos_da_ficha(self.exercicios):
            itens = []
            for exercicio in bloco.exercicios:
                ultima = self.ultimas.get(exercicio.id)
                itens.append({
                    'exercicio': exercicio,
                    'ultima_sessao': ultima[0] if ultima else None,
                    'ultimas_series': ultima[1] if ultima else [],
                    'series': [
                        {
                            'numero': numero,
                            'feita': self['feita-' + chave],
                            'carga': self['carga-' + chave],
                            'valor': self[('tempo-' if exercicio.tempo_segundos else 'reps-') + chave],
                        }
                        for numero in self.numeros(exercicio)
                        for chave in [self.chave(exercicio, numero)]
                    ],
                })
            yield {'combinado': bloco.combinado, 'itens': itens}



# =====================================================================
# Registrar treino (treino livre): tela do protótipo App Saúde/Registro de treino
# =====================================================================

EXERCICIOS_LIVRES_MAXIMOS = 30


class RegistrarTreinoForm(forms.Form):
    nome = forms.CharField(
        label='Nome do treino', max_length=100,
        error_messages={'required': 'Dê um nome para o treino.'},
        widget=forms.TextInput(attrs={'placeholder': 'Ex.: Treino A — peito e tríceps'}),
    )
    esporte = forms.ModelChoiceField(
        label='Tipo', queryset=None, widget=forms.RadioSelect, empty_label=None,
        error_messages={'required': 'Escolha o tipo do treino.'},
    )
    data = forms.DateField(label='Data', widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    hora = forms.TimeField(label='Horário', widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time'}))
    duracao = forms.IntegerField(
        label='Duração', min_value=1, max_value=600,
        widget=forms.NumberInput(attrs={'placeholder': '60', 'min': 1, 'max': 600, 'inputmode': 'numeric'}),
    )
    intensidade = forms.ChoiceField(label='Intensidade', choices=INTENSIDADES.items(), widget=forms.RadioSelect)
    distancia = forms.DecimalField(
        label='Distância (opcional)', min_value=Decimal('0.01'), max_value=999, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '5', 'step': 'any', 'min': 0, 'inputmode': 'decimal'}),
    )
    observacoes = forms.CharField(
        label='Observações (opcional)', max_length=2000, required=False,
        widget=forms.Textarea(attrs={'placeholder': 'Como você se sentiu, ajustes de carga, dores...', 'rows': 3}),
    )

    def __init__(self, esportes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['esporte'].queryset = Esporte.objects.filter(id__in=[e.id for e in esportes])
        # mantém a ordem "do perfil primeiro" nos chips
        self.fields['esporte'].choices = [(e.id, e.nome) for e in esportes]
        self.fields['data'].widget.attrs['max'] = timezone.localdate().isoformat()

    def clean_nome(self):
        nome = ' '.join(self.cleaned_data['nome'].split())
        if not nome:
            raise forms.ValidationError('Dê um nome para o treino.')
        return nome

    def clean(self):
        dados = super().clean()
        if dados.get('data') and dados.get('hora'):
            inicio = timezone.make_aware(datetime.combine(dados['data'], dados['hora']))
            if inicio > timezone.now() + TOLERANCIA_FUTURO:
                self.add_error('hora' if dados['data'] == timezone.localdate() else 'data',
                               'O treino não pode ser no futuro.')
            dados['inicio'] = inicio
        return dados


class ExercicioLivreForm(forms.Form):
    """Um exercício do treino livre: nome, séries, repetições e carga. Linha vazia é ignorada."""
    nome = forms.CharField(
        label='Nome do exercício', max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Nome do exercício'}),
    )
    series = forms.IntegerField(
        label='Séries', min_value=1, max_value=20, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '4', 'min': 1, 'max': 20, 'inputmode': 'numeric'}),
    )
    repeticoes = forms.IntegerField(
        label='Repetições', min_value=1, max_value=REPETICOES_MAXIMAS, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '12', 'min': 1, 'max': REPETICOES_MAXIMAS, 'inputmode': 'numeric'}),
    )
    carga = forms.DecimalField(
        label='Carga (kg)', min_value=0, max_value=CARGA_MAXIMA, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'placeholder': '40', 'step': 'any', 'min': 0, 'inputmode': 'decimal'}),
    )

    def clean(self):
        dados = super().clean()
        dados['nome'] = ' '.join((dados.get('nome') or '').split())
        numeros = [dados.get(c) for c in ('series', 'repeticoes', 'carga')]
        if not dados['nome']:
            if any(n is not None for n in numeros):
                self.add_error('nome', 'Dê um nome ao exercício.')
            return dados
        if not dados.get('series') and 'series' not in self.errors:
            self.add_error('series', 'Quantas séries?')
        if not dados.get('repeticoes') and 'repeticoes' not in self.errors:
            self.add_error('repeticoes', 'Quantas repetições?')
        return dados


class BaseExerciciosLivres(forms.BaseFormSet):
    def exercicios(self):
        return [
            ExercicioLivre(
                nome=f.cleaned_data['nome'],
                series=f.cleaned_data['series'],
                repeticoes=f.cleaned_data['repeticoes'],
                carga_kg=f.cleaned_data.get('carga') or Decimal('0'),
            )
            for f in self.forms
            if f.cleaned_data.get('nome')
        ]


ExerciciosLivresFormSet = forms.formset_factory(
    ExercicioLivreForm, formset=BaseExerciciosLivres, extra=1,
    max_num=EXERCICIOS_LIVRES_MAXIMOS, absolute_max=EXERCICIOS_LIVRES_MAXIMOS, validate_max=True,
)
