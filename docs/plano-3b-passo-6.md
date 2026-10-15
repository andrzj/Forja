# Plano do passo 6 do 3b: `MutationCheck` (gate 7)

Decisões do dono (14/10/2026): o check muta só o que o diff alterou; limiar de nota **0,65** para Python; o check nasce em `OBSERVATION` (Especificação, linha 288) e só vira bloqueante por decisão registrada na política, depois da calibração do passo 9.

## Achado que muda a premissa

O dono respondeu que o mapa linha→testes vem do `GateInput`. Hoje isso não é verdade. `GateInput` (`core/gates/check.py`) carrega `Evidence`, que é escalar (`value: bool | int | float | str`), e `PipelineMeasurer.judge()` o monta sem `base_evidence` nem `attempt_evidence`. Não há onde um `CoverageReport` caiba.

Caminho proposto, que segue o padrão dos checks existentes (`ComplexityCheck`, `TestsCheck`): o `MutationCheck` recebe suas dependências no construtor (`tools`, `adapter`, `worktree`, `changes`, arquivos de produção alterados) e roda a operação `COVERAGE` do adaptador por conta própria, lendo o relatório com `read_coverage`. `GateInput.values` só traz limiar e limites. Ficar com o mapa dentro do `GateInput` exigiria um tipo novo no contrato central, e isso é decisão do dono (ver "Decisões abertas", item 1).

## Fluxo do `evaluate`

1. Sem arquivo de produção Python alterado: `Approved()`.
2. Linhas alteradas por arquivo: `added_lines(patch)` de `checks/changes.py` (devolve `path`, `number`, `text`). Confirmar de onde sai o patch (outros checks já o leem).
3. Cobertura: rodar `COVERAGE` pelo adaptador (relatório em `target/coverage/python/coverage.json`) e ler com `read_coverage(ReportFormat.COVERAGE_PY_JSON, ...)`, obtendo `FileCoverage.tests` por linha. Falha da ferramenta: `Inconclusive(TOOL_FAILED)`.
4. Sites: `discover(source)` de `mutation/sites.py` em cada arquivo alterado; ficar com os sites cuja linha está nas linhas alteradas.
5. Mutantes: para cada site, `apply_site(source, site)` gera os bytes; `Mutant(file, line, change=site.description, function, mutated, tests)` com `tests` vindo do mapa. Sem teste na linha: `tests=()`, que vira `UNCOVERED`.
6. Executor: `run_mutants(worktree, scratch, mutants, runner, workers=...)`. `BaselineFailed` vira `Inconclusive`.
7. Nota: `MutationReport.score` contra o limiar (padrão 0,65). `None` (nenhum mutante) é `Approved`. Abaixo do limiar: `Rejected` com um `Finding` por arquivo ou função e `measured`/`limit`, mais os mutantes sobreviventes (até `MAX_FINDINGS`).
8. Supressões: `mutation-suppressions.toml` é do gate de desenvolvimento da Forja, não do produto. Não aplicar aqui.

## `TestRunner` do Python

O executor pede `runner(root, selectors, timeout) -> TestVerdict`. O adaptador Python filtra por arquivo (`test_files`), não por função. Os contextos do coverage.py são nomes de função de teste sem o diretório. Falta o passo contexto→arquivo de teste (ver "Decisões abertas", item 2). O runner usa `Tools`/`CommandPlan` do adaptador (mesmo caminho dos outros checks), com `PYTHONDONTWRITEBYTECODE` fora do ambiente da mitigação, como no passo 5.

## Registro e política

- `checks/specs.py::default_registry()`: `CheckSpec("mutation", 7, Mode.OBSERVATION, PREMISE, thresholds=frozenset({"min_score"}), limits=frozenset({"workers", "timeout_factor"}))`. Usar `PREMISE` como no `complexity`, porque o limiar não está calibrado. Confirmar se `limits` aceita esses nomes.
- Padrões: `min_score` = 0,65 (Python), workers = `min(4, núcleos)` (valor atual do executor), timeout = 3× canário, piso de 10 s.
- `PipelineMeasurer.judge()` (`orchestrator/measurer.py`, ~linha 256): acrescentar `MutationCheck(...)` à lista, depois de `TestsCheck` e antes de `ComplexityCheck`. Capacidades exigidas: `coverage` e `mutation`; confirmar que o `PythonAdapter` declara a segunda (hoje vi só `COVERAGE` na linha 66 de `adapter.py`).

## Testes (`tests/checks/test_mutation.py`, local a confirmar)

- Aprovado: mutantes mortos acima de 0,65.
- Reprovado: sobreviventes abaixo de 0,65, com findings.
- Sem arquivo alterado e sem mutante: `Approved`.
- Linha alterada sem teste: `UNCOVERED` conta contra a nota.
- Mutação só nas linhas do diff; linhas antigas do mesmo arquivo ficam de fora.
- Falha da cobertura e `BaselineFailed`: `Inconclusive`.
- Modo `OBSERVATION` não bloqueia, mas reporta (cobrir no teste do pipeline).
- Conformância/registro: `default_registry()` inclui `mutation` no gate 7.

## Fora do escopo

`CrapCheck` (passo 7), métricas opostas (passo 8), calibração e mutação diferencial dos alvos do 3a (passo 9), aceitação (passo 10). Leitores de outras linguagens e `defusedxml` seguem como estão.

## Decisões tomadas na implementação (dono delegou: 14/10/2026)

1. Mapa fora do `GateInput`: o check roda a cobertura sozinho.
2. Teste por arquivo: o `coverage_driver.py` agora grava o `nodeid` do pytest (`tests/test_a.py::test_x`) como contexto, no lugar do `test_function` do coverage.py (`test_a.test_x`, sem diretório). O arquivo é a parte antes de `::`. Linha coberta sem teste atribuído roda todos os arquivos de teste do relatório.
3. Cobertura completa a cada tentativa, aceita em `OBSERVATION`; relatório apagado do worktree depois de lido.
4. Ferramenta que não roda: `PREMISE`.
5. Capacidade exigida: só `coverage` (o motor de mutação é da Forja, não do adaptador). Workers: `limits.workers` ou o padrão do executor.

Código: `src/forja/checks/mutation.py`; testes: `tests/checks/test_mutation.py`.

## Decisões abertas (perguntas ao dono) — RESOLVIDAS, ver acima

1. O mapa linha→testes fica fora do `GateInput`, com o check rodando a cobertura sozinho (proposto), ou o contrato central ganha um campo para relatórios?
2. Contexto→arquivo de teste: resolver pelos nomes de contexto do coverage.py (precisa descobrir o arquivo de cada função) ou rodar o arquivo de teste inteiro que contém cada contexto? A primeira é mais precisa; a segunda é mais simples. Proposta: segunda.
3. Custo: rodar cobertura completa a cada tentativa pode ser lento. Aceitável em `OBSERVATION`, ou limitar a cobertura aos testes ligados aos arquivos alterados?
4. `PREMISE` ou `BLOCK` para o caso de a ferramenta não rodar?
