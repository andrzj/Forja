# Forja

<p align="center">
  <img src="https://img.shields.io/static/v1?label=Python&message=3.12%2B&color=blue&style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/static/v1?label=uv&message=gerenciador&color=blue&style=for-the-badge"/>
  <img src="https://img.shields.io/static/v1?label=Plataforma&message=Windows%20e%20Linux&color=lightgrey&style=for-the-badge"/>
  <img src="https://img.shields.io/static/v1?label=License&message=a%20definir&color=lightgrey&style=for-the-badge"/>
  <img src="https://img.shields.io/static/v1?label=STATUS&message=EM%20DESENVOLVIMENTO&color=red&style=for-the-badge"/>
</p>

> Status do projeto: em desenvolvimento. A fila do [Plano de execução](docs/Plano%20de%20execu%C3%A7%C3%A3o.md) está concluída; o que ainda falta está nas [Tarefas em aberto](#tarefas-em-aberto).

### Tópicos

- [Descrição do projeto](#descrição-do-projeto)
- [Funcionalidades](#funcionalidades)
- [Pré-requisitos](#pré-requisitos)
- [Como rodar a aplicação](#como-rodar-a-aplicação)
- [Como rodar os testes](#como-rodar-os-testes)
- [Casos de uso](#casos-de-uso)
- [Configurando a execução](#configurando-a-execução)
- [Linguagens, dependências e libs utilizadas](#linguagens-dependências-e-libs-utilizadas)
- [Resolvendo problemas](#resolvendo-problemas)
- [Tarefas em aberto](#tarefas-em-aberto)
- [Documentação](#documentação)
- [Desenvolvedores e contribuintes](#desenvolvedores-e-contribuintes)
- [Licença](#licença)

## Descrição do projeto

<p align="justify">
  A Forja é uma ferramenta de linha de comando, escrita em Python, que conduz CLIs de agentes de código (Claude Code, Codex, OpenCode e outras) para criar, refatorar, corrigir e documentar software. O LLM faz apenas o trabalho probabilístico, e a ferramenta exige dele fatos verificáveis.
</p>

<p align="justify">
  Tudo o que pode ser medido ou verificado por máquina é executado pela própria Forja e funciona como gate, não como instrução. A Forja substitui arquivos de instrução (AGENTS.md, CLAUDE.md e similares) por medições que reprovam a entrega.
</p>

## Funcionalidades

- Quatro objetivos: `refatorar`, `corrigir`, `investigar` e `criar`.
- Uma branch por execução, uma worktree por tentativa e um commit por etapa. O agente trabalha numa cópia sem `.git`.
- Gates de escopo, segredos, formato, lint, build, testes, vermelho/verde, congelamento de testes, mutação, complexidade, arquitetura, segurança, teste diferencial, duplicação e tipos.
- Papéis de implementador, autor de testes, documentador, especificador e arqueólogo.
- Documentação gerada junto com cada tarefa: README, registro de mudança e ADR.
- Retomada de execuções interrompidas, sem perder o que foi salvo.
- Interface de terminal com progresso, atividade do agente, detalhes (`d`) e log (`l`); modo texto para CI.
- Instalação das ferramentas externas pelo próprio comando `forja instalar`.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/): instala a Forja e o Python 3.12 que ela exige. O Python do sistema pode ser mais antigo, então use sempre `uv run` em vez de `python`.
- [git](https://git-scm.com/downloads): a Forja não o instala; `forja doctor` o verifica.
- A CLI do agente (por exemplo o Claude Code), com o seu login. A Forja não instala a CLI nem faz o login.
- Rede, na instalação das ferramentas externas.
- Windows ou Linux (WSL). macOS está suspenso.

## Como rodar a aplicação

O pacote ainda não está publicado em registro. A partir de uma cópia do repositório:

```bash
uv tool install .
forja doctor
forja instalar
```

`forja doctor` só verifica e diz o que falta. `forja instalar` baixa as ferramentas que faltam e, rodado de novo, não baixa o que já está instalado.

Para executar, entre no repositório alvo e rode:

```bash
forja
```

A Forja pergunta o que fazer, mostra a confirmação e começa. Detalhes de instalação, atualização e remoção em [docs/instalacao.md](docs/instalacao.md).

## Como rodar os testes

```bash
uv sync                                  # cria o ambiente e instala as dependências
uv run pytest -q -m "not slow"           # suíte sem os testes lentos
uv run pytest -q                         # suíte completa
uv run ruff format . && uv run ruff check .
uv run mypy                              # modo strict
uv run python scripts/mutate.py          # gate de mutação nos arquivos alterados desde o HEAD
```

Os testes marcados com `slow` são os de `tests/e2e/test_resume.py` e `tests/e2e/test_resume_hard.py`. Os marcadores `tools`, `integration` e `live` estão declarados em `pyproject.toml`.

## Casos de uso

Refatorar um pacote em CI, sem perguntas, com um `execucao.toml`:

```bash
forja --config execucao.toml
```

```toml
objetivo = "refatorar"
cli = "claude-code"
escopo = ["src/meuapp"]
tokens = 2000000
tarefas = 5

[interface]
modo = "texto"
```

Corrigir um defeito, investigar uma pergunta ou criar um projeto a partir de uma ideia mudam só o `objetivo`. O guia completo do modo CI, com todas as chaves, está em [docs/modo-ci.md](docs/modo-ci.md).

## Configurando a execução

- `execucao.toml`: guarda as respostas da preparação (objetivo, CLI, escopo, limite de tokens, número de tarefas, paralelismo). Chave desconhecida recusa o arquivo.
- `forja.toml`: valores dos gates (limiares, modo observação ou bloqueante, comandos). Predicados e lógica ficam no código.
- `FORJA_HOME`: onde ficam as ferramentas instaladas pela Forja.

Limiares e modos em [docs/limiares.md](docs/limiares.md).

## Linguagens, dependências e libs utilizadas

Linguagens que a Forja conduz: Python, TypeScript, JavaScript, Go, Java (Maven e Gradle) e C#.

Dependências de execução do pacote:

- [pydantic](https://docs.pydantic.dev/) (esquemas validados)
- [rich](https://github.com/Textualize/rich) e [Textual](https://textual.textualize.io/) (interface)
- [ruff](https://docs.astral.sh/ruff/) (lint e formato de Python)
- [lizard](https://github.com/terryyin/lizard) (complexidade)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/) com as gramáticas das seis linguagens (mutação)

Ferramentas externas instaladas por `forja instalar`: gitleaks, osv-scanner, jscpd e Semgrep, mais as de cada linguagem detectada. Desenvolvimento: `pytest`, `mypy`, `coverage`, `pytest-xdist` e `pytest-timeout`.

## Resolvendo problemas

- `forja doctor` mostra o que falta no ambiente.
- Execução incompleta bloqueia `--config` no mesmo repositório: rode `forja` sem `--config` e escolha retomar ou descartar.
- Limites conhecidos e decisões de projeto: [docs/estado.md](docs/estado.md) e os [registros de decisão (ADRs)](docs/adr/README.md).

## Tarefas em aberto

- Publicar o pacote em registro (hoje a instalação é a partir do repositório).
- Suporte a macOS (suspenso).
- Outras CLIs de agente além do Claude Code estão fora do escopo atual.
- Licença a definir.

## Documentação

- [Especificação](docs/Especifica%C3%A7%C3%A3o.md): visão, princípios e modos de operação.
- [Plano de execução](docs/Plano%20de%20execu%C3%A7%C3%A3o.md): fila, regras e registro de andamento.
- [Instalar a Forja](docs/instalacao.md): instalação, `forja instalar`, atualizar e remover.
- [Modo CI](docs/modo-ci.md): execução sem perguntas e `execucao.toml`.
- [Segurança e dependências](docs/seguranca-e-dependencias.md): o gate 10 e os limites dos registros.
- [Duplicação (DRY)](docs/duplicacao.md): o gate de código repetido (`jscpd`).
- [Tipos do Python](docs/tipos.md): o check de análise estática (`mypy`).
- [Teste de propriedades](docs/teste-de-propriedades.md): a biblioteca de cada linguagem e o check `properties`.
- [Registros de decisão (ADRs)](docs/adr/README.md): índice das decisões de arquitetura.

Convenções de desenvolvimento: código, comentários e docstrings em inglês; README e ADRs em português do Brasil; `mypy` em modo strict; `ruff` com linha de 100 colunas.

## Desenvolvedores e contribuintes

O histórico de autoria está no git: `git shortlog -sn`.

## Licença

Licença: a definir.
