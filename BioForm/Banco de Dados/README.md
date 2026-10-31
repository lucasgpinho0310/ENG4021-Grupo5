# BioForm — banco de dados (Django)

Tabelas criadas a partir de `App Saúde/modelagemDados.txt`, seguindo a aula
*Atividade 03 — Modelagem de Dados*. Projeto Django `bioform`, app `saude`
(as tabelas estão em `saude/models.py` e as telas do admin em `saude/admin.py`).

O app `contas` (login, cadastro e perfil) também fica aqui. Os apps de cada sprint ficam nas suas
pastas e são carregados por `bioform/settings.py`: `diario`, `medidas_caseiras` e `metas` em
`BioForm/Sprint-6`; `rotina` e `treinos` em `BioForm/Sprint-7`.

| Domínio | Tabelas |
|---|---|
| Identidade e perfil | `usuarios`, `esportes`, `esportes_usuario` |
| Evolução | `historico_medidas` |
| Nutrição | `metas_nutricionais`, `catalogo_alimentos`, `medidas_caseiras`, `refeicoes_personalizadas`, `refeicoes_personalizadas_itens`, `diario_consumo`, `registros_refeicao`, `registros_refeicao_itens` |
| Treino e atividades | `fichas_treino`, `exercicios_ficha`, `sessoes_atividade`, `series_executadas_historico` |
| Gamificação social | `perfil_gamificacao`, `historico_xp`, `amizades`, `grupos`, `membros_grupo`, `desafios`, `participantes_desafio` |

## Como rodar

### No GitHub Codespaces

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/lucasgpinho0310/ENG4021-Grupo5)

No GitHub: **Code → Codespaces → Create codespace on main**. Ao abrir, o Codespace instala o
Django, cria as tabelas e liga o servidor na porta 8000 sozinho (configuração em
`.devcontainer/devcontainer.json`). O site abre numa aba de pré-visualização; para abrir no
navegador, use a aba **Portas** → porta 8000 → ícone do globo.

Para criar o administrador, rode num terminal novo:

```bash
cd "BioForm/Banco de Dados"
python manage.py createsuperuser
```

### No computador

```bash
cd "BioForm/Banco de Dados"
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac/Replit: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate        # cria as tabelas e já popula alimentos, esportes e medidas caseiras
python manage.py createsuperuser
python manage.py runserver
```

Site: http://127.0.0.1:8000/ · Admin: http://127.0.0.1:8000/admin/

Testes: `python manage.py test saude contas diario medidas_caseiras metas rotina treinos`

As imagens enviadas nos exercícios ficam em `media/` (fora do git).

## Dados que já vêm carregados

**Alimentos** (`0002_popular_alimentos_taco`): **591 alimentos** da
**TACO — Tabela Brasileira de Composição de Alimentos** (NEPA/UNICAMP, 4ª ed., 2011),
com kcal, proteína, carboidrato e gordura **por 100 g**.

- Dados: `saude/dados/alimentos_taco.csv` (extraído de
  [raulfdm/taco-api](https://github.com/raulfdm/taco-api), licença MIT).
- Valores ausentes na TACO por serem traço ou "não se aplica" (ex.: proteína do azeite) foram gravados como 0.
- 6 alimentos sem nenhuma análise na TACO ficaram de fora (ex.: leite integral, coco verde).

**Esportes** (`0003_popular_esportes`): os 10 esportes do mockup e das regras de negócio, com um
MET de referência aproximado (Compendium of Physical Activities) para o cálculo do gasto.
Dá para ajustar os valores pelo admin.

Rodar `migrate` de novo não duplica nada (cada registro tem UUID fixo).

## Regras que já estão no banco

- Um diário de consumo por usuário por dia; um perfil de gamificação por usuário.
- Amizade sem par repetido e sem amizade consigo mesmo; um esporte só uma vez por perfil.
- Desafio não pode terminar antes de começar; CPF com 11 números.
- Nascimento, sexo, altura e biotipo podem ficar vazios no banco (migração `0004`), porque a conta é
  criada antes do perfil ser preenchido.
- `RegistroRefeicaoItem.macros()` calcula kcal e macros do que foi comido (em medida caseira ou porção).
- `Grupo.ranking_semanal(dia)` ordena os membros pelo XP da semana (segunda a domingo).
- `PerfilGamificacao.nivel()` devolve o patamar (Semente, Bronze, Prata, Ouro, Diamante).

## Ainda falta

- Não modelados: diário de bem-estar (humor, dores, sono) e lembretes (RF16).
