# Aceitação do Incremento 1

Critério de pronto do plano: três repositórios Python de exemplo vão do comando à entrega sem
intervenção; interrupções forçadas em qualquer passo retomam e chegam ao mesmo estado final; uma CLI
que tenta usar git falha; a preparação e o resumo declaram o que a Forja impõe e o que fica por conta
do ambiente; a própria Forja passa nos seus gates.

Cada linha aponta a prova (um teste ou um comando) e o resultado da última rodada. Atualizar a cada
rodada.

| Critério | Prova | Resultado |
| --- | --- | --- |
| Três repositórios, do comando à entrega | `tests/acceptance/test_samples.py` (função simples, vários módulos, método de classe), agente falso, git, ruff, pytest e lizard reais | Passa |
| Uma execução com o Claude Code real | `FORJA_LIVE=1` (provas de vida e contenção) e uma execução do usuário (roteiro abaixo) | Provas de vida e contenção passam. A execução completa com a CLI real **ainda não foi feita** |
| Interrupção em qualquer passo retoma ao mesmo estado final | `tests/orchestrator/test_resume_end_to_end.py` (cortes em cada fronteira de evento, linhas rasgadas, processo congelado); `tests/acceptance/test_resume.py` (corte no meio da chamada do agente, retomar, descartar) | Passa |
| Uma CLI que tenta usar git falha | `tests/acceptance/test_git_forbidden.py`: `git` na cópia, `git -C` no repositório real e `--git-dir` são barrados ou pegos; a execução para com o motivo; `tests/cli/test_facade.py` | Passa |
| Preparação e resumo declaram o imposto e o do ambiente | A confirmação (`prepare.summary_of`) e a seção "Ambiente e garantias" do `resumo.md` (`tests/orchestrator/test_details.py`) | Passa |
| A Forja passa nos seus gates | Comandos abaixo | **Parcial**, ver abaixo |

## Os gates sobre a própria Forja (rodada de 11/10/2026)

| Gate | Comando | Resultado |
| --- | --- | --- |
| Formato | `uv run ruff format --check src tests` | Passa (295 arquivos) |
| Lint | `uv run ruff check src tests` | Passa |
| Tipos em `src` | `uv run mypy src` | Passa (143 arquivos) |
| Tipos em `tests` | `uv run mypy src tests` | **32 erros** em 12 arquivos antigos de `tests/` |
| Testes | `uv run pytest` | Passa; 4 testes são deselecionados no Linux por falharem lá |
| Complexidade (limite 15) | `uv run python -m lizard src -C 15 -w` | **8 funções acima do limite**: `gitguard/rules.py check` (25), `policy/config.py _validate_redaction` (27), `redaction/engine.py _matches` (25), `budget.py read_consumption` (18), `isolation/sensitive.py compile_pattern` (17), `theme.py _ansi` (17), `ui/plain.py update` (16), `policy/config.py _merge` (16) |
| Segredos | `gitleaks` | **Não executado**: o gitleaks não está instalado nesta máquina |
| Mutação | `scripts/mutate.py --all` | Adiada para o segundo plano (a Forja avaliando a si mesma); o módulo `1b` segue sem confirmação completa |

Decisão registrada: os pontos abaixo ficam como dívida declarada, tratada no segundo plano e não
neste incremento.

- as 8 funções complexas;
- os 32 erros de tipo em `tests/`;
- o gitleaks sobre o repositório;
- a mutação completa.

## Roteiro da execução real

Precisa do Claude Code instalado e logado, do gitleaks no PATH e de um repositório git pequeno, limpo e
com uma função complexa (CCN acima de 15). Gasta tokens do seu plano; o limite padrão é de 2.000.000.

```bash
forja doctor
forja refatorar --plano
forja refatorar
```

Depois: conferir `git log --oneline forja-run/<id>`, abrir o `resumo.md` (caminho no fim da execução) e
mandar o resumo para a próxima rodada desta tabela.
