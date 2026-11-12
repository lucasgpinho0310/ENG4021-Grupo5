"""
python manage.py popular_exemplo

Povoa o banco com 3 pessoas de exemplo e o que cada uma registrou nas últimas semanas, para o site e o
admin já abrirem com dados (apresentações, testes à mão, prints):

- perfil completo, esportes, metas, pesagens semanais (gráfico de evolução do peso)
- séries de academia, treinos feitos com carga subindo (histórico, "Última vez", recordes)
- corridas e outros treinos livres ("Registrar treino"), com distância e observações
- diário alimentar dos últimos dias, com água e check-in de dieta
- combos de refeição salvos (café da manhã de sempre)
- gamificação: XP, sequência, amizade, um grupo com as três e um desafio

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

PESSOAS = [
    {
        'email': 'ana' + DOMINIO, 'nome': 'Ana Souza', 'apelido': 'Ana', 'nascimento': date(1998, 4, 12),
        'sexo': 'feminino', 'altura': 165, 'biotipo': 'endomorfo', 'objetivo': 'emagrecimento',
        'peso_inicial': Decimal('72.0'), 'peso_semanal': Decimal('-0.6'), 'peso_meta': Decimal('64'),
        'esportes': [('Musculação', 3, 'moderada', 60, 'seg,qua,sex'), ('Corrida', 2, 'leve', 45, 'ter,sab')],
        'fichas': [('Treino A · Inferiores', 'seg,sex', TREINO_INFERIORES),
                   ('Treino B · Superiores', 'qua', TREINO_SUPERIORES)],
        'corrida_km': Decimal('5'),
    },
    {
        'email': 'bruno' + DOMINIO, 'nome': 'Bruno Lima', 'apelido': 'Bruno', 'nascimento': date(2002, 9, 3),
        'sexo': 'masculino', 'altura': 180, 'biotipo': 'ectomorfo', 'objetivo': 'hipertrofia',
        'peso_inicial': Decimal('74.0'), 'peso_semanal': Decimal('0.4'), 'peso_meta': Decimal('80'),
        'esportes': [('Musculação', 4, 'intensa', 60, 'seg,ter,qui,sex'), ('Futebol', 1, 'intensa', 90, 'sab')],
        'fichas': [('Treino A · Inferiores', 'seg,qui', TREINO_INFERIORES),
                   ('Treino B · Superiores', 'ter,sex', TREINO_SUPERIORES)],
        'corrida_km': None,
    },
    {
        'email': 'carla' + DOMINIO, 'nome': 'Carla Mendes', 'apelido': 'Carla', 'nascimento': date(1990, 1, 25),
        'sexo': 'feminino', 'altura': 160, 'biotipo': 'mesomorfo', 'objetivo': 'saude',
        'peso_inicial': Decimal('61.0'), 'peso_semanal': Decimal('-0.1'), 'peso_meta': None,
        'esportes': [('Corrida', 3, 'moderada', 45, 'ter,qui,sab'), ('Yoga', 2, 'leve', 60, 'seg,qua')],
        'fichas': [],
        'corrida_km': Decimal('7.5'),
    },
]

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
    help = 'Povoa o banco com 3 pessoas de exemplo (@exemplo.com) e semanas de treinos, diário e pesagens.'

    def handle(self, *args, **opcoes):
        self.hoje = timezone.localdate()
        self.alimentos = {}
        with transaction.atomic():
            apagadas = get_user_model().objects.filter(username__endswith=DOMINIO)
            if apagadas.exists():
                self.stdout.write('Apagando %d conta(s) de exemplo antigas...' % apagadas.count())
                apagadas.delete()  # o perfil e tudo dele vão junto (CASCADE)
            usuarios = [self.criar_pessoa(i, dados) for i, dados in enumerate(PESSOAS)]
            self.criar_social(usuarios)

        self.stdout.write(self.style.SUCCESS('\nPronto! Contas de exemplo (senha: %s):' % SENHA))
        for usuario in usuarios:
            self.stdout.write('  %-20s %s' % (usuario.conta.email, usuario.nome_completo))
        self.stdout.write('\nEntre no site com uma delas ou veja tudo no admin (/admin/).')

    # ----------------------------------------------------------------- pessoa
    def criar_pessoa(self, indice, dados):
        conta = get_user_model().objects.create_user(
            username=dados['email'], email=dados['email'], password=SENHA,
            first_name=dados['apelido'], last_name=dados['nome'].split()[-1],
        )
        usuario = Usuario.objects.create(
            conta=conta, nome_completo=dados['nome'], apelido=dados['apelido'],
            cpf=cpf_valido('91234567%d' % indice), celular='2199999000%d' % indice, aceitou_termos=True,
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
        self.criar_diario(usuario)
        self.stdout.write('  %s: %d treinos, %d dias de diário, %d pesagens' % (
            dados['apelido'], SessaoAtividade.objects.filter(usuario=usuario).count(),
            DiarioConsumo.objects.filter(usuario=usuario).count(),
            HistoricoMedida.objects.filter(usuario=usuario).count(),
        ))
        return usuario

    # ----------------------------------------------------------------- treinos
    def criar_treinos(self, usuario, dados):
        fichas = [
            treinos.criar_ficha(usuario, nome, dias.split(','), True, ler_texto(texto).exercicios)
            for nome, dias, texto in dados['fichas']
        ]
        progresso = Decimal('1.0')
        for semana in range(SEMANAS, -1, -1):  # da mais antiga até esta semana (dias futuros ficam de fora)
            segunda = self.hoje - timedelta(weeks=semana, days=self.hoje.weekday())
            for n, ficha in enumerate(fichas):
                dia = segunda + timedelta(days=n * 2)
                if dia >= self.hoje:
                    continue
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
                sessoes.registrar_treino(usuario, ficha, momento(dia, 18), 60, 'moderada', feitos)
            progresso += Decimal('0.04')  # a carga sobe ~4% por semana: aparecem recordes no histórico

            if dados['corrida_km']:
                dia = segunda + timedelta(days=1)
                if dia < self.hoje:
                    km = dados['corrida_km'] + Decimal('0.5') * (SEMANAS - semana)
                    sessoes.registrar_treino_livre(
                        usuario, Esporte.objects.get(nome='Corrida'), momento(dia, 7), int(km * 6), 'moderada',
                        nome='Corrida na Lagoa', distancia_km=km,
                        observacoes='Ritmo confortável, último km mais forte.' if semana == 1 else '',
                    )
        if dados['apelido'] == 'Carla':
            ontem = self.hoje - timedelta(days=1)
            sessoes.registrar_treino_livre(
                usuario, Esporte.objects.get(nome='Funcional'), momento(ontem, 19), 45, 'intensa',
                nome='Funcional no parque',
                observacoes='Circuito com a turma. Joelho tranquilo.',
                exercicios=[sessoes.ExercicioLivre('Burpee', 4, 12), sessoes.ExercicioLivre('Afundo', 3, 12, Decimal('6')),
                            sessoes.ExercicioLivre('Flexão de braço', 3, 15)],
            )

    # ----------------------------------------------------------------- diário
    def alimento(self, comeco):
        if comeco not in self.alimentos:
            self.alimentos[comeco] = Alimento.objects.filter(nome__istartswith=comeco).order_by('nome').first()
        return self.alimentos[comeco]

    def criar_diario(self, usuario):
        for dias_atras in range(6, -1, -1):
            dia = self.hoje - timedelta(days=dias_atras)
            refeicoes = CARDAPIO if dias_atras else CARDAPIO[:2]  # hoje: só café e almoço, o resto "ainda falta"
            for tipo, itens in refeicoes:
                for comeco, porcoes in itens:
                    alimento = self.alimento(comeco)
                    if alimento:
                        diario.registrar_item(usuario, dia, tipo, alimento, porcoes)
            diario.adicionar_agua(usuario, dia, 2000 if dias_atras else 1000)
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
        ana, bruno, carla = usuarios
        Amizade.objects.create(usuario_1=ana, usuario_2=bruno)
        Amizade.objects.create(usuario_1=ana, usuario_2=carla)
        grupo = Grupo.objects.create(
            nome='Turma ENG4021', descricao='Grupo de exemplo do BioForm', criador=ana, codigo_convite='ENG4021EXE',
        )
        for usuario in usuarios:
            MembroGrupo.objects.create(grupo=grupo, usuario=usuario, papel='admin' if usuario == ana else 'membro')
            sequencia = 0
            for dias_atras in range(13, -1, -1):
                dia = self.hoje - timedelta(days=dias_atras)
                RegistroXP.objects.create(usuario=usuario, acao='checkin_refeicao', pontos=10, data_referencia=dia)
                if dia.weekday() in (0, 2, 4):
                    RegistroXP.objects.create(usuario=usuario, acao='treino', pontos=50, data_referencia=dia)
                sequencia += 1
            pontos = sum(r.pontos for r in usuario.registros_xp.all())
            PerfilGamificacao.objects.create(
                usuario=usuario, streak_atual=sequencia, pontos_experiencia=pontos,
                escudos_descanso=sequencia // 15, ultimo_dia_ativo=self.hoje,
            )
        segunda = self.hoje - timedelta(days=self.hoje.weekday())
        desafio = Desafio.objects.create(
            grupo=grupo, criador=bruno, nome='Quem treina mais no mês', metrica='sessoes',
            descricao='Vale musculação, corrida e qualquer treino registrado.',
            data_inicio=segunda.replace(day=1), data_fim=segunda.replace(day=1) + timedelta(days=30),
        )
        for usuario in usuarios:
            ParticipanteDesafio.objects.create(desafio=desafio, usuario=usuario)
