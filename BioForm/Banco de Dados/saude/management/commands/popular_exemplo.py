"""
python manage.py popular_exemplo

Povoa o banco com 11 personas bem diferentes entre si e o que cada uma registrou nas últimas semanas,
para o site e o admin já abrirem com dados e para mostrar que o app serve para todo mundo:
idades de 16 a 74 anos, homens e mulheres, corpos e biotipos diferentes, os quatro objetivos,
os 10 esportes do catálogo, um atleta cadeirante, uma pessoa vegetariana, quem está começando agora
e quem usa o app só de vez em quando.

Para cada persona:

- perfil completo, esportes, metas, pesagens semanais (gráfico de evolução do peso)
- séries de academia, treinos feitos com carga subindo (histórico, "Última vez", recordes)
- corridas e outros treinos livres ("Registrar treino"), com distância e observações
- diário alimentar dos últimos dias, com água e check-in de dieta
- combos de refeição salvos (café da manhã de sempre)
- gamificação: XP, sequência, amizades, dois grupos e dois desafios

Os alimentos (TACO), esportes e medidas caseiras já vêm das migrações 0002, 0003 e medidas_caseiras 0001.
Rodar de novo apaga e recria só as contas de exemplo (e-mails @exemplo.com); o resto do banco não muda.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from diario import servicos as diario
from evolucao.servicos import registrar_pesagem
from metas.calculo import salvar_meta
from saude.models import (
    Alimento,
    Amizade,
    Desafio,
    DiarioConsumo,
    Esporte,
    EsporteUsuario,
    Grupo,
    HistoricoMedida,
    MembroGrupo,
    ParticipanteDesafio,
    PerfilGamificacao,
    RegistroRefeicao,
    RegistroXP,
    SessaoAtividade,
    Usuario,
)
from treinos import servicos as treinos
from treinos import sessoes
from treinos.leitor import ler_texto

SENHA = 'bioform2026'
DOMINIO = '@exemplo.com'
SEMANAS = 6

TREINO_INFERIORES = """Agachamento livre
Séries: 4x10
Carga: 40kg
Intervalo: 90s

Leg press 45
Séries: 4x12
Carga: 120kg
Intervalo: 90s

Cadeira extensora
Séries: 3x12
Carga: 35kg

Prancha
Séries: 3x40s
Carga: 0kg
"""

TREINO_SUPERIORES = """Supino reto
Séries: 4x10
Carga: 30kg
Intervalo: 90s

Puxada frontal
Séries: 4x12
Carga: 40kg

Desenvolvimento com halteres
Séries: 3x12
Carga: 10kg

Rosca direta
Séries: 3x12
Carga: 12kg
"""

TREINO_FORCA_60 = """Cadeira extensora
Séries: 2x12
Carga: 15kg
Intervalo: 90s

Leg press 45
Séries: 2x12
Carga: 40kg
Intervalo: 90s

Remada sentada na máquina
Séries: 2x12
Carga: 20kg

Elevação lateral
Séries: 2x12
Carga: 2kg

Prancha
Séries: 2x20s
Carga: 0kg
"""

TREINO_ADAPTADO = """Supino com halteres
Séries: 4x10
Carga: 16kg
Intervalo: 90s

Puxada frontal
Séries: 4x12
Carga: 45kg

Remada baixa
Séries: 3x12
Carga: 40kg

Desenvolvimento sentado
Séries: 3x10
Carga: 12kg

Tríceps na polia
Séries: 3x12
Carga: 20kg
"""

TREINO_INICIANTE = """Leg press 45
Séries: 3x12
Carga: 50kg
Intervalo: 90s

Puxada frontal
Séries: 3x12
Carga: 25kg

Supino na máquina
Séries: 3x12
Carga: 20kg

Prancha
Séries: 3x20s
Carga: 0kg
"""

# Refeições de um dia: (tipo, [(começo do nome do alimento na TACO, porções de 100 g)])
CARDAPIO = [
    ('cafe_manha', [('Pão, trigo, francês', Decimal('0.5')), ('Ovo, de galinha, inteiro, cozido', Decimal('1')),
                    ('Banana, prata', Decimal('1'))]),
    ('almoco', [('Arroz, tipo 1, cozido', Decimal('1.5')), ('Feijão, carioca, cozido', Decimal('1')),
                ('Frango, peito, sem pele, grelhado', Decimal('1.2')), ('Alface', Decimal('0.3'))]),
    ('lanche_tarde', [('Iogurte, natural', Decimal('1.7')), ('Aveia, flocos', Decimal('0.3'))]),
    ('jantar', [('Batata, doce, cozida', Decimal('1.5')), ('Carne, bovina, patinho, sem gordura, grelhado', Decimal('1')),
                ('Tomate, com semente', Decimal('0.8'))]),
]

# Mais leve e com mais fibras (pessoas 60+)
CARDAPIO_LEVE = [
    ('cafe_manha', [('Pão, trigo, forma, integral', Decimal('0.5')), ('Queijo, minas, frescal', Decimal('0.3')),
                    ('Mamão, Papaia', Decimal('1.5')), ('Café, infusão', Decimal('1'))]),
    ('almoco', [('Arroz, integral, cozido', Decimal('1')), ('Feijão, preto, cozido', Decimal('0.8')),
                ('Sardinha, assada', Decimal('1')), ('Abobrinha, italiana, cozida', Decimal('1')),
                ('Cenoura, cozida', Decimal('0.5'))]),
    ('lanche_tarde', [('Iogurte, natural, desnatado', Decimal('1.5')), ('Laranja, pêra', Decimal('1.2'))]),
    ('jantar', [('Batata, inglesa, cozida', Decimal('1.5')), ('Chuchu, cozido', Decimal('1')),
                ('Ovo, de galinha, inteiro, cozido', Decimal('0.5'))]),
]

# Vegetariano (ovolactovegetariano): proteína de lentilha, ovo, iogurte e queijo
CARDAPIO_VEGETARIANO = [
    ('cafe_manha', [('Pão, trigo, forma, integral', Decimal('0.5')), ('Abacate', Decimal('0.5')),
                    ('Café, infusão', Decimal('1'))]),
    ('almoco', [('Arroz, integral, cozido', Decimal('1.5')), ('Lentilha, cozida', Decimal('1.2')),
                ('Brócolis, cozido', Decimal('1')), ('Cenoura, cozida', Decimal('0.5'))]),
    ('lanche_tarde', [('Iogurte, natural', Decimal('1.7')), ('Castanha-do-Brasil', Decimal('0.15')),
                      ('Banana, prata', Decimal('1'))]),
    ('jantar', [('Cuscuz, de milho', Decimal('1.5')), ('Ovo, de galinha, inteiro, cozido', Decimal('1')),
                ('Queijo, minas, frescal', Decimal('0.3')), ('Tomate, com semente', Decimal('0.8'))]),
]

# Dias da semana como nos campos dias_fixos / dias_semana
DIAS = {'seg': 0, 'ter': 1, 'qua': 2, 'qui': 3, 'sex': 4, 'sab': 5, 'dom': 6}


def livre(esporte, dia, hora, minutos, intensidade, nome, km=None, km_semana=None, exercicios=(), obs=''):
    """Um treino livre que a persona registra toda semana em "Registrar treino"."""
    return {'esporte': esporte, 'dia': dia, 'hora': hora, 'minutos': minutos, 'intensidade': intensidade,
            'nome': nome, 'km': km, 'km_semana': km_semana, 'exercicios': exercicios, 'obs': obs}


# Cada persona: perfil, esportes (nome, vezes/semana, intensidade, minutos, dias), séries de academia
# (nome, dias, texto, fator de carga), treinos livres semanais, cardápio, dias de diário e dias seguidos de uso.
PESSOAS = [
    {
        'email': 'ana' + DOMINIO, 'nome': 'Ana Souza', 'apelido': 'Ana', 'nascimento': date(1998, 4, 12),
        'sexo': 'feminino', 'altura': 165, 'biotipo': 'endomorfo', 'objetivo': 'emagrecimento',
        'peso_inicial': Decimal('72.0'), 'peso_semanal': Decimal('-0.6'), 'peso_meta': Decimal('64'),
        'resumo': 'universitária, quer emagrecer com academia e corrida',
        'esportes': [('Musculação', 3, 'moderada', 60, 'seg,qua,sex'), ('Corrida', 2, 'leve', 45, 'ter,sab')],
        'fichas': [('Treino A · Inferiores', 'seg,sex', TREINO_INFERIORES, Decimal('1')),
                   ('Treino B · Superiores', 'qua', TREINO_SUPERIORES, Decimal('1'))],
        'livres': [livre('Corrida', 'ter', 7, 30, 'moderada', 'Corrida na Lagoa', Decimal('5'), Decimal('0.5'),
                         obs='Ritmo confortável, último km mais forte.')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2000, 'sequencia': 14,
    },
    {
        'email': 'bruno' + DOMINIO, 'nome': 'Bruno Lima', 'apelido': 'Bruno', 'nascimento': date(2002, 9, 3),
        'sexo': 'masculino', 'altura': 180, 'biotipo': 'ectomorfo', 'objetivo': 'hipertrofia',
        'peso_inicial': Decimal('74.0'), 'peso_semanal': Decimal('0.4'), 'peso_meta': Decimal('80'),
        'resumo': 'quer ganhar massa; academia 4x e futebol no sábado',
        'esportes': [('Musculação', 4, 'intensa', 60, 'seg,ter,qui,sex'), ('Futebol', 1, 'intensa', 90, 'sab')],
        'fichas': [('Treino A · Inferiores', 'seg,qui', TREINO_INFERIORES, Decimal('1.3')),
                   ('Treino B · Superiores', 'ter,sex', TREINO_SUPERIORES, Decimal('1.4'))],
        'livres': [livre('Futebol', 'sab', 10, 90, 'intensa', 'Pelada com os amigos')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2500, 'sequencia': 21,
    },
    {
        'email': 'carla' + DOMINIO, 'nome': 'Carla Mendes', 'apelido': 'Carla', 'nascimento': date(1990, 1, 25),
        'sexo': 'feminino', 'altura': 160, 'biotipo': 'mesomorfo', 'objetivo': 'saude',
        'peso_inicial': Decimal('61.0'), 'peso_semanal': Decimal('-0.1'), 'peso_meta': None,
        'resumo': 'corre e faz yoga pela saúde, sem meta de peso',
        'esportes': [('Corrida', 3, 'moderada', 45, 'ter,qui,sab'), ('Yoga', 2, 'leve', 60, 'seg,qua')],
        'fichas': [],
        'livres': [livre('Corrida', 'ter', 7, 45, 'moderada', 'Corrida na Lagoa', Decimal('7.5'), Decimal('0.5')),
                   livre('Yoga', 'seg', 19, 60, 'leve', 'Yoga em casa'),
                   livre('Funcional', 'qui', 19, 45, 'intensa', 'Funcional no parque',
                         exercicios=[('Burpee', 4, 12, 0), ('Afundo', 3, 12, 6), ('Flexão de braço', 3, 15, 0)],
                         obs='Circuito com a turma. Joelho tranquilo.')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2000, 'sequencia': 10,
    },
    {
        'email': 'lucia' + DOMINIO, 'nome': 'Lúcia Ferreira', 'apelido': 'Dona Lúcia', 'nascimento': date(1958, 6, 2),
        'sexo': 'feminino', 'altura': 155, 'biotipo': 'endomorfo', 'objetivo': 'saude',
        'peso_inicial': Decimal('78.0'), 'peso_semanal': Decimal('-0.2'), 'peso_meta': None,
        'resumo': 'aposentada; natação e alongamento para a saúde das articulações',
        'esportes': [('Natação', 2, 'leve', 45, 'ter,qui'), ('Yoga', 1, 'leve', 50, 'sab')],
        'fichas': [],
        'livres': [livre('Natação', 'ter', 8, 45, 'leve', 'Natação no clube do bairro', Decimal('0.6'), Decimal('0.05'),
                         obs='Nado livre e costas, sem dor no joelho.'),
                   livre('Natação', 'qui', 8, 45, 'leve', 'Hidroginástica'),
                   livre('Yoga', 'sab', 9, 50, 'leve', 'Alongamento e yoga na praça')],
        'cardapio': CARDAPIO_LEVE, 'dias_diario': 7, 'agua': 1500, 'sequencia': 30,
    },
    {
        'email': 'antonio' + DOMINIO, 'nome': 'Antônio Pereira', 'apelido': 'Seu Antônio', 'nascimento': date(1952, 3, 18),
        'sexo': 'masculino', 'altura': 168, 'biotipo': 'mesomorfo', 'objetivo': 'manutencao',
        'peso_inicial': Decimal('70.0'), 'peso_semanal': Decimal('0'), 'peso_meta': None,
        'resumo': 'musculação leve 2x por semana para manter força e equilíbrio',
        'esportes': [('Musculação', 2, 'leve', 40, 'seg,qui')],
        'fichas': [('Força 60+ · Corpo inteiro', 'seg,qui', TREINO_FORCA_60, Decimal('1'))],
        'livres': [],
        'cardapio': CARDAPIO_LEVE, 'dias_diario': 7, 'agua': 1500, 'sequencia': 12,
    },
    {
        'email': 'rafael' + DOMINIO, 'nome': 'Rafael Costa', 'apelido': 'Rafael', 'nascimento': date(1995, 11, 7),
        'sexo': 'masculino', 'altura': 175, 'biotipo': 'mesomorfo', 'objetivo': 'hipertrofia',
        'peso_inicial': Decimal('68.0'), 'peso_semanal': Decimal('0.2'), 'peso_meta': Decimal('72'),
        'resumo': 'cadeirante; treino adaptado de superiores e natação',
        'esportes': [('Musculação', 3, 'moderada', 60, 'seg,qua,sex'), ('Natação', 1, 'moderada', 45, 'sab')],
        'fichas': [('Treino adaptado · Superiores', 'seg,qua,sex', TREINO_ADAPTADO, Decimal('1'))],
        'livres': [livre('Natação', 'sab', 9, 45, 'moderada', 'Natação adaptada', Decimal('0.8'), Decimal('0.1'),
                         obs='Nado com flutuador nas pernas. Ombros bem.')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2000, 'sequencia': 18,
    },
    {
        'email': 'juliana' + DOMINIO, 'nome': 'Juliana Oliveira', 'apelido': 'Ju', 'nascimento': date(2010, 2, 14),
        'sexo': 'feminino', 'altura': 162, 'biotipo': 'ectomorfo', 'objetivo': 'saude',
        'peso_inicial': Decimal('52.0'), 'peso_semanal': Decimal('0.1'), 'peso_meta': None,
        'resumo': 'joga vôlei no time da escola',
        'esportes': [('Vôlei', 3, 'moderada', 90, 'ter,qui,sab'), ('Funcional', 1, 'moderada', 45, 'seg')],
        'fichas': [],
        'livres': [livre('Vôlei', 'ter', 16, 90, 'moderada', 'Treino de vôlei da escola'),
                   livre('Vôlei', 'sab', 9, 120, 'intensa', 'Jogo do campeonato escolar'),
                   livre('Funcional', 'seg', 17, 45, 'moderada', 'Funcional na escola')],
        'cardapio': CARDAPIO, 'dias_diario': 5, 'agua': 1800, 'sequencia': 6,
    },
    {
        'email': 'marcos' + DOMINIO, 'nome': 'Marcos Santos', 'apelido': 'Marcos', 'nascimento': date(1980, 8, 30),
        'sexo': 'masculino', 'altura': 172, 'biotipo': 'endomorfo', 'objetivo': 'emagrecimento',
        'peso_inicial': Decimal('118.0'), 'peso_semanal': Decimal('-0.8'), 'peso_meta': Decimal('95'),
        'resumo': 'começando agora: bike e academia para iniciantes, perdendo peso com calma',
        'esportes': [('Ciclismo', 2, 'leve', 40, 'seg,sab'), ('Musculação', 2, 'leve', 45, 'ter,qui')],
        'fichas': [('Iniciante · Corpo inteiro', 'ter,qui', TREINO_INICIANTE, Decimal('1'))],
        'livres': [livre('Ciclismo', 'sab', 7, 40, 'leve', 'Pedal na ciclovia', Decimal('8'), Decimal('1'),
                         obs='Primeira vez sem parar no caminho!')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2500, 'sequencia': 9,
    },
    {
        'email': 'beatriz' + DOMINIO, 'nome': 'Beatriz Nakamura', 'apelido': 'Bia', 'nascimento': date(1999, 5, 21),
        'sexo': 'feminino', 'altura': 158, 'biotipo': 'ectomorfo', 'objetivo': 'hipertrofia',
        'peso_inicial': Decimal('49.0'), 'peso_semanal': Decimal('0.2'), 'peso_meta': Decimal('53'),
        'resumo': 'quer ganhar massa; academia e jiu-jitsu',
        'esportes': [('Musculação', 4, 'intensa', 60, 'seg,ter,qui,sex'), ('Lutas', 2, 'intensa', 90, 'qua,sab')],
        'fichas': [('Treino A · Inferiores', 'seg,qui', TREINO_INFERIORES, Decimal('0.8')),
                   ('Treino B · Superiores', 'ter,sex', TREINO_SUPERIORES, Decimal('0.5'))],
        'livres': [livre('Lutas', 'qua', 19, 90, 'intensa', 'Jiu-jitsu', obs='Treino de passagem de guarda.')],
        'cardapio': CARDAPIO, 'dias_diario': 7, 'agua': 2200, 'sequencia': 25,
    },
    {
        'email': 'thiago' + DOMINIO, 'nome': 'Thiago Almeida', 'apelido': 'Thiago', 'nascimento': date(1988, 12, 9),
        'sexo': 'masculino', 'altura': 178, 'biotipo': 'mesomorfo', 'objetivo': 'manutencao',
        'peso_inicial': Decimal('82.0'), 'peso_semanal': Decimal('0'), 'peso_meta': None,
        'resumo': 'usa o app de vez em quando: futevôlei no fim de semana',
        'esportes': [('Futevôlei', 1, 'moderada', 120, 'sab')],
        'fichas': [],
        'livres': [livre('Futevôlei', 'sab', 9, 120, 'moderada', 'Futevôlei na praia')],
        'cardapio': CARDAPIO, 'dias_diario': 2, 'agua': 1500, 'sequencia': 2,
    },
    {
        'email': 'fernanda' + DOMINIO, 'nome': 'Fernanda Ribeiro', 'apelido': 'Fernanda', 'nascimento': date(1993, 7, 4),
        'sexo': 'feminino', 'altura': 167, 'biotipo': 'mesomorfo', 'objetivo': 'saude',
        'peso_inicial': Decimal('63.0'), 'peso_semanal': Decimal('0'), 'peso_meta': None,
        'resumo': 'vegetariana; corrida e yoga',
        'esportes': [('Corrida', 2, 'moderada', 40, 'ter,qui'), ('Yoga', 2, 'leve', 60, 'seg,sex')],
        'fichas': [],
        'livres': [livre('Corrida', 'qui', 6, 30, 'moderada', 'Corrida no Aterro', Decimal('4'), Decimal('0.3')),
                   livre('Yoga', 'seg', 7, 60, 'leve', 'Yoga no estúdio')],
        'cardapio': CARDAPIO_VEGETARIANO, 'dias_diario': 7, 'agua': 2000, 'sequencia': 16,
    },
]

# Quem está em qual grupo (o primeiro é quem criou) e as amizades, pelos e-mails sem o domínio
GRUPOS = [
    ('Turma ENG4021', 'Grupo de exemplo do BioForm', 'ENG4021EXE',
     ['ana', 'bruno', 'carla', 'beatriz', 'thiago', 'fernanda', 'rafael'],
     ('Quem treina mais no mês', 'sessoes', 'Vale musculação, corrida e qualquer treino registrado.')),
    ('Movimento 60+', 'Para quem quer se cuidar em qualquer idade', 'MOV60MAIS',
     ['lucia', 'antonio', 'marcos'],
     ('Mais dias bebendo água', 'agua', 'Quem bater a meta de água em mais dias do mês.')),
]
AMIZADES = [('ana', 'bruno'), ('ana', 'carla'), ('bruno', 'beatriz'), ('bruno', 'rafael'), ('bruno', 'thiago'),
            ('carla', 'fernanda'), ('lucia', 'antonio'), ('marcos', 'rafael'), ('marcos', 'lucia')]


def cpf_valido(base):
    """CPF com dígitos verificadores certos a partir de 9 dígitos (o cadastro valida)."""
    digitos = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(d * p for d, p in zip(digitos, range(tamanho + 1, 1, -1)))
        digitos.append((soma * 10 % 11) % 10)
    return ''.join(map(str, digitos))


def momento(dia, hora):
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


class Command(BaseCommand):
    help = 'Povoa o banco com %d personas de exemplo (@exemplo.com) e semanas de treinos, diário e pesagens.' % len(PESSOAS)

    def handle(self, *args, **opcoes):
        self.hoje = timezone.localdate()
        self.alimentos = {}
        with transaction.atomic():
            apagadas = get_user_model().objects.filter(username__endswith=DOMINIO)
            if apagadas.exists():
                self.stdout.write('Apagando %d conta(s) de exemplo antigas...' % apagadas.count())
                apagadas.delete()  # o perfil e tudo dele vão junto (CASCADE)
            usuarios = {
                dados['email'].split('@')[0]: self.criar_pessoa(i, dados) for i, dados in enumerate(PESSOAS)
            }
            self.criar_social(usuarios)

        self.stdout.write(self.style.SUCCESS('\nPronto! %d contas de exemplo (senha de todas: %s):' % (len(PESSOAS), SENHA)))
        for dados in PESSOAS:
            idade = self.hoje.year - dados['nascimento'].year - (
                (self.hoje.month, self.hoje.day) < (dados['nascimento'].month, dados['nascimento'].day))
            self.stdout.write('  %-22s %s, %d anos: %s' % (dados['email'], dados['nome'], idade, dados['resumo']))
        self.stdout.write('\nEntre no site com uma delas ou veja tudo no admin (/admin/).')

    # ----------------------------------------------------------------- pessoa
    def criar_pessoa(self, indice, dados):
        conta = get_user_model().objects.create_user(
            username=dados['email'], email=dados['email'], password=SENHA,
            first_name=dados['apelido'], last_name=dados['nome'].split()[-1],
        )
        usuario = Usuario.objects.create(
            conta=conta, nome_completo=dados['nome'], apelido=dados['apelido'],
            cpf=cpf_valido('9123456%02d' % indice), celular='219999900%02d' % indice, aceitou_termos=True,
            data_nascimento=dados['nascimento'], sexo_biologico=dados['sexo'], altura_cm=dados['altura'],
            peso_meta_kg=dados['peso_meta'], biotipo=dados['biotipo'], rotina_confirmada_em=self.hoje,
        )
        for nome, vezes, intensidade, minutos, dias in dados['esportes']:
            EsporteUsuario.objects.create(
                usuario=usuario, esporte=Esporte.objects.get(nome=nome), frequencia_semanal=vezes,
                intensidade=intensidade, duracao_minutos=minutos, dias_fixos=dias,
            )

        # Pesagens: uma por semana, a primeira há SEMANAS semanas; a última recalcula as metas
        inicio = self.hoje - timedelta(weeks=SEMANAS)
        HistoricoMedida.objects.create(
            usuario=usuario, data_registro=momento(inicio, 7), peso_kg=dados['peso_inicial'],
            objetivo_momento=dados['objetivo'],
        )
        salvar_meta(usuario)
        for semana in range(1, SEMANAS + 1):
            peso = dados['peso_inicial'] + dados['peso_semanal'] * semana
            registrar_pesagem(usuario, inicio + timedelta(weeks=semana), peso.quantize(Decimal('0.1')))

        self.criar_treinos(usuario, dados)
        self.criar_diario(usuario, dados)
        self.stdout.write('  %-12s %2d treinos, %d dias de diário, %d pesagens' % (
            dados['apelido'], SessaoAtividade.objects.filter(usuario=usuario).count(),
            DiarioConsumo.objects.filter(usuario=usuario).count(),
            HistoricoMedida.objects.filter(usuario=usuario).count(),
        ))
        return usuario

    # ----------------------------------------------------------------- treinos
    def criar_treinos(self, usuario, dados):
        fichas = []
        for nome, dias, texto, fator in dados['fichas']:
            exercicios = ler_texto(texto).exercicios
            for exercicio in exercicios:  # a mesma série serve para gente mais forte ou mais leve
                exercicio.carga_kg = (exercicio.carga_kg * fator).quantize(Decimal('0.5'))
            fichas.append((treinos.criar_ficha(usuario, nome, dias.split(','), True, exercicios), dias.split(',')))
        intensidade = {e[0]: e[2] for e in dados['esportes']}.get('Musculação', 'moderada')
        duracao = {e[0]: e[3] for e in dados['esportes']}.get('Musculação', 60)

        progresso = Decimal('1.0')
        for semana in range(SEMANAS, -1, -1):  # da mais antiga até esta semana (dias futuros ficam de fora)
            segunda = self.hoje - timedelta(weeks=semana, days=self.hoje.weekday())
            for ficha, dias in fichas:
                for dia_semana in dias:
                    dia = segunda + timedelta(days=DIAS[dia_semana])
                    if dia >= self.hoje:
                        continue
                    sessoes.registrar_treino(
                        usuario, ficha, momento(dia, 18), duracao, intensidade, self.series_feitas(ficha, progresso, semana),
                    )
            progresso += Decimal('0.04')  # a carga sobe ~4% por semana: aparecem recordes no histórico

            for treino in dados['livres']:
                dia = segunda + timedelta(days=DIAS[treino['dia']])
                if dia >= self.hoje:
                    continue
                km = treino['km'] + treino['km_semana'] * (SEMANAS - semana) if treino['km'] else None
                sessoes.registrar_treino_livre(
                    usuario, Esporte.objects.get(nome=treino['esporte']), momento(dia, treino['hora']),
                    treino['minutos'], treino['intensidade'], nome=treino['nome'], distancia_km=km,
                    observacoes=treino['obs'] if semana <= 1 else '',
                    exercicios=[sessoes.ExercicioLivre(nome, series, reps, Decimal(carga))
                                for nome, series, reps, carga in treino['exercicios']],
                )

    def series_feitas(self, ficha, progresso, semana):
        feitos = []
        for exercicio in ficha.exercicios.order_by('ordem_execucao'):
            carga = (exercicio.carga_kg * progresso).quantize(Decimal('0.5'))
            series = [
                sessoes.SerieFeita(
                    n_serie, carga,
                    repeticoes=None if exercicio.tempo_segundos else max(exercicio.repeticoes_planejadas - (n_serie > 2), 1),
                    tempo_segundos=exercicio.tempo_segundos + 5 * (SEMANAS - semana) if exercicio.tempo_segundos else None,
                )
                for n_serie in range(1, exercicio.series_planejadas + 1)
            ]
            feitos.append((exercicio, series))
        return feitos

    # ----------------------------------------------------------------- diário
    def alimento(self, comeco):
        if comeco not in self.alimentos:
            self.alimentos[comeco] = Alimento.objects.filter(nome__istartswith=comeco).order_by('nome').first()
        return self.alimentos[comeco]

    def criar_diario(self, usuario, dados):
        for dias_atras in range(dados['dias_diario'] - 1, -1, -1):
            dia = self.hoje - timedelta(days=dias_atras)
            cardapio = dados['cardapio']
            refeicoes = cardapio if dias_atras else cardapio[:2]  # hoje: só café e almoço, o resto "ainda falta"
            for tipo, itens in refeicoes:
                for comeco, porcoes in itens:
                    alimento = self.alimento(comeco)
                    if alimento:
                        diario.registrar_item(usuario, dia, tipo, alimento, porcoes)
            diario.adicionar_agua(usuario, dia, dados['agua'] if dias_atras else dados['agua'] // 2)
            if dias_atras and dias_atras % 2 == 0:
                diario.confirmar_dieta(usuario, dia)
        # O café da manhã de hoje vira um combo, como o botão "Salvar esta refeição como combo"
        cafe = RegistroRefeicao.objects.filter(
            diario__usuario=usuario, diario__data_referencia=self.hoje, tipo_refeicao='cafe_manha',
        ).first()
        if cafe:
            diario.salvar_combo(usuario, cafe.id, 'Café da manhã de sempre')

    # ----------------------------------------------------------------- social
    def criar_social(self, usuarios):
        for um, outro in AMIZADES:
            Amizade.objects.create(usuario_1=usuarios[um], usuario_2=usuarios[outro])

        for dados in PESSOAS:  # XP: um check-in por dia da sequência, mais 50 nos dias de treino
            usuario = usuarios[dados['email'].split('@')[0]]
            dias_de_treino = {DIAS[d] for e in dados['esportes'] for d in e[4].split(',')}
            for dias_atras in range(dados['sequencia'] - 1, -1, -1):
                dia = self.hoje - timedelta(days=dias_atras)
                RegistroXP.objects.create(usuario=usuario, acao='checkin_refeicao', pontos=10, data_referencia=dia)
                if dia.weekday() in dias_de_treino:
                    RegistroXP.objects.create(usuario=usuario, acao='treino', pontos=50, data_referencia=dia)
            PerfilGamificacao.objects.create(
                usuario=usuario, streak_atual=dados['sequencia'],
                pontos_experiencia=sum(r.pontos for r in usuario.registros_xp.all()),
                escudos_descanso=dados['sequencia'] // 15, ultimo_dia_ativo=self.hoje,
            )

        inicio_do_mes = self.hoje.replace(day=1)
        for nome, descricao, codigo, membros, (desafio_nome, metrica, desafio_descricao) in GRUPOS:
            criador = usuarios[membros[0]]
            grupo = Grupo.objects.create(nome=nome, descricao=descricao, criador=criador, codigo_convite=codigo)
            for apelido in membros:
                MembroGrupo.objects.create(grupo=grupo, usuario=usuarios[apelido],
                                           papel='admin' if apelido == membros[0] else 'membro')
            desafio = Desafio.objects.create(
                grupo=grupo, criador=criador, nome=desafio_nome, metrica=metrica, descricao=desafio_descricao,
                data_inicio=inicio_do_mes, data_fim=inicio_do_mes + timedelta(days=30),
            )
            for apelido in membros:
                ParticipanteDesafio.objects.create(desafio=desafio, usuario=usuarios[apelido])
