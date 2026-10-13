# Aceitação do 3a — autor de testes, gate vermelho/verde e congelamento

Data: 13/10/2026. Passo 9 do `docs\plano-3.md`. Todos os números abaixo vêm de execuções feitas nesta data, no commit `685daac` mais o novo `tests\executors\test_live_fix.py`.

## Resultado

Os quatro critérios do passo 9 foram atendidos. A execução viva usou 2 dos 4 repositórios (`pager` e `money`), o mínimo exigido.

| Critério | Evidência | Resultado |
|---|---|---|
| Cada teste ruim é rejeitado com a causa certa | `tests\checks\test_red_green_defects.py::test_every_bad_test_is_rejected`, 20 casos (4 repositórios × 5 testes ruins), pytest real | 20 de 20 rejeitados |
| O teste bom passa | Mesmo arquivo: `test_the_reference_tests_are_red_on_the_defect` (4 casos) e `test_the_reference_tests_are_rejected_once_the_defect_is_fixed` (4 casos) | 8 de 8 |
| Alterar teste congelado reprova | `tests\checks\test_freeze.py` (8 testes: alterado, apagado, movido, arquivo novo ignorado pelo git, mudança não listada, diretório removido). `tests\orchestrator\test_fix_task.py` confere que o `frozen_digest` chega ao implementador | passam |
| Execução viva com o Claude Code nos dois papéis, em ao menos 2 de 4 repositórios | `tests\executors\test_live_fix.py` com `FORJA_LIVE=1` | 2 de 2 passaram |

Execução dos arquivos sem tokens (`test_red_green_defects`, `test_red_green`, `test_freeze`, `test_fix_task`): 54 passaram em 16,6 s.

## Causa de rejeição de cada teste ruim

O teste confere a mensagem do gate, não só a rejeição. Em todos os repositórios:

| Teste ruim | Causa registrada pelo gate |
|---|---|
| `test_ruim_erro_importacao` | `the declared test errors out instead of failing (import or collection)` |
| `test_ruim_assercao_fraca` | `the declared test passes on the code with the defect` |
| `test_ruim_assert_true` | `the declared test passes on the code with the defect` |
| `test_ruim_nao_chama` | `the declared test passes on the code with the defect` |
| `test_ruim_sem_assercao` | `the declared test passes on the code with the defect` |

O gate não distingue `AssertionError` de outra exceção (o parser de pytest não guarda o tipo da exceção). Um teste que falha por erro de lógica dele mesmo, e não pelo defeito, é aceito como vermelho.

## Execução viva

Comando: `FORJA_LIVE=1 uv run pytest tests/executors/test_live_fix.py -s --timeout=1800`. Duração total: 49 s. Teto autorizado pelo dono: 200 mil tokens por chamada do agente.

| Repositório | Papel | Tokens | Gate |
|---|---|---|---|
| `pager` | autor de testes | 10.802 | `RedGreenCheck` aprovou |
| `pager` | implementador | 7.851 | `FreezeCheck` e `TestsCheck` aprovaram |
| `money` | autor de testes | 9.291 | `RedGreenCheck` aprovou |
| `money` | implementador | 8.397 | `FreezeCheck` e `TestsCheck` aprovaram |

Total: 36.341 tokens, cerca de 18% do teto de uma única chamada. Uma tentativa por papel em cada repositório, sem repetição.

## O que a execução viva não prova

- Só uma execução por repositório. Não há taxa de sucesso, só a prova de que o caminho funciona.
- Os repositórios `spans` e `slugs` não rodaram ao vivo. Os testes ruins e a referência deles foram verificados só pelo pytest real, sem o agente.
- O teste vivo monta o `FreezeCheck` com `Changes` vazio, porque a cópia de trabalho não tem git real. Um congelamento violado pelo agente seria reprovado só com a mensagem genérica (`the frozen tests were changed`), sem nomear o arquivo. O caso com nome de arquivo está coberto em `test_freeze.py`.
- O teto de tokens é conferido ao fim de cada chamada. O runner não tem como interromper uma chamada em andamento.
- A execução viva chama o autor e o implementador direto, sem passar por `TaskCycle`, pelo git real nem pelo commit de etapa. A integração dessas peças está coberta pelos testes de `tests\orchestrator`, com agente roteirizado, não ao vivo.
- Mutação diferencial dos arquivos do 3a: adiada para o 3b por decisão do dono.

## Pendências observadas (fora do escopo do passo)

- `TEST_ROOT = "tests"` é constante assumida em `planner.py`; o dono não definiu a origem.
- A mensagem do `ScopeCheck` do implementador diz "in a refactoring" mesmo numa correção.
- `mypy src scripts` falha por módulo `core` duplicado em `scripts\medicao\defeitos\*\corrigido\core.py`.
- Execução com tarefa bloqueada ainda termina `DELIVERED`.
