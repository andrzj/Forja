# Forja

## O que é a Forja

A Forja é uma ferramenta de linha de comando, escrita em Python, que conduz CLIs de agentes de código (Claude Code, Codex, OpenCode e outras) para criar, refatorar, manter e documentar software. O LLM faz apenas o trabalho probabilístico, e a ferramenta exige dele fatos verificáveis. Tudo o que pode ser medido ou verificado por máquina é executado pela própria Forja e funciona como gate, não como instrução. A Forja substitui arquivos de instrução (AGENTS.md, CLAUDE.md e similares) por medições que reprovam a entrega.

## Estado atual

O incremento 0 (fundação) está quase completo. Os cinco contratos centrais existem como código e têm testes. Também existem o lock por repositório, as interfaces de adaptador, a redação do pacote e um teste de retomada ponta a ponta. Os incrementos 1 a 7 ainda não foram iniciados. Não há CLI utilizável.

O plano completo está em [Plano de execução](docs/Plano%20de%20execu%C3%A7%C3%A3o.md). O estado detalhado, com decisões e limitações, está em [docs/estado.md](docs/estado.md).

## Como executar

Pré-requisito: uv. O `uv sync` instala o Python 3.12 que o projeto exige. O Python do sistema pode ser mais antigo (3.11 na máquina de referência), então use sempre `uv run` em vez de `python`.

```bash
uv sync                          # cria o ambiente e instala as dependências
uv run pytest -q                 # roda a suíte completa
uv run pytest -q -m "not slow"   # pula os testes lentos
uv run ruff format . && uv run ruff check .
uv run mypy                      # modo strict
```

A suíte completa leva cerca de 6 minutos. Os testes marcados com `slow` (o marcador está declarado em `pyproject.toml`) são os de `tests/e2e/test_resume.py` e `tests/e2e/test_resume_hard.py`, e levam cerca de 4 minutos. Use `-m "not slow"` no ciclo de desenvolvimento diário e rode a suíte completa antes de uma entrega.

## Mapa dos módulos (`src/forja/core/`)

- `states/`: máquinas de estado puras dos quatro níveis (execução, tarefa, etapa, tentativa).
- `process/`: `ProcessRunner` assíncrono, com timeout, cancelamento, log bruto e validação de comando.
- `idempotency/`: tabela das 10 operações externas, reconciliadores e o auxiliar `Git`.
- `manifest.py`: manifesto de uma cópia de trabalho e a diferença entre manifestos.
- `events/`: log JSONL com hash encadeado; o estado é reconstruído a partir dos eventos.
- `artifacts/`: cabeçalho, armazenamento por hash, tipos de corpo e contrato de saída do LLM.
- `evidence/`: `ToolRun`, `Evidence`, chave de cache e `EvidenceCache`.
- `records.py`: armazenamento genérico de registros imutáveis.
- `gates/`: resultados dos gates, matriz modo × resultado, `GatePipeline` e registro de decisão.
- `policy/`: camadas de política em TOML, validação, congelamento em `policy.json` e versão.
- `authorization/`, `isolation/`, `gitguard/`, `confirmation.py`: classes de ação, níveis de isolamento, ambiente filtrado, `GuardedGit` e fotografia do git.
- `locking/`: lock por repositório, mutex de git e remoção de `index.lock` órfão.
- `adapters/`: interfaces de adaptador de linguagem e de executor, registro e `TemplateExecutorAdapter`.
- `redaction/`: redação do pacote antes do envio e registro do que foi enviado.
- `resume.py`: retomada de execuções interrompidas.
- `atomic.py`, `ids.py`, `paths.py`, `failures.py`, `version.py`: utilitários.

Os testes ficam em `tests/core/`, espelhando a estrutura dos módulos. O arquivo `tests/core/adapters/conformance.py` é a suíte reutilizável que todo adaptador real deve passar. Os testes de ponta a ponta ficam em `tests/e2e/`.

## Convenções

- Código, comentários e docstrings em inglês.
- README e ADRs em português do Brasil.
- Dependência de execução: apenas `pydantic>=2.7`. Dependências de desenvolvimento: `pytest`, `ruff` e `mypy`. Não adicione outras sem decisão registrada, porque a especificação restringe o conjunto.
- `mypy` em modo strict, configurado para `src` e `tests`.
- `ruff` com comprimento de linha 100.
- Valores de estado gravados no JSONL usam nomes em inglês (por exemplo, `in_progress`). A tabela de correspondência está em `docs/estado.md`.

## Plataformas

Até agora a Forja só foi executada no Windows. Os ramos POSIX (`process/_posix.py`, grupos de processo e leitura de `/proc`) existem, mas não foram exercitados. Não há suporte a WSL.

## Documentação

- [Especificação](docs/Especifica%C3%A7%C3%A3o.md): visão, princípios e modos de operação.
- [Plano de execução](docs/Plano%20de%20execu%C3%A7%C3%A3o.md): incrementos e questões abertas.
- [Estado do incremento 0](docs/estado.md): como trabalhar, decisões que complementam a especificação, armadilhas e limitações conhecidas.
- [Segurança e dependências](docs/seguranca-e-dependencias.md): o gate 10, o que você precisa fornecer (regras do Semgrep, licenças proibidas) e os limites dos registros.
- [Registros de decisão (ADRs)](docs/adr/README.md): índice das decisões de arquitetura.

## Licença

Licença: a definir.
