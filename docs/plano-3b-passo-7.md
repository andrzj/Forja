# Plano do passo 7 do 3b: `CrapCheck` (gate 8)

Contexto: a Especificação (linhas 354 e 407) pede CRAP calculado de complexidade e cobertura por
método, lidas das ferramentas. O gate 8 hoje só tem `ComplexityCheck`. O passo 7 acrescenta o CRAP;
métricas opostas (pass-through, profundidade de módulo) ficam no passo 8.

## Fatos lidos no código

- `checks\complexity.py`: lizard em CSV. `parse_functions` guarda só `(arquivo, função) → CCN` e
  descarta as colunas `from`/`to` (índices 9 e 10 de `FIELDS`). A regra "só reprova função nova ou
  que piorou" (`old is None or ccn > old`) e `_origin` (renomeação) já existem.
- `core\reports\models.py::FileCoverage.fraction(lines)` já devolve a fração de linhas executáveis
  cobertas em um conjunto de linhas, ou `None` se nenhuma é executável.
- `checks\mutation.py::MutationCheck._coverage` roda a cobertura, lê o relatório e apaga o arquivo.
  Está presa à classe: o CRAP precisaria copiar esse código.
- `checks\specs.py`: `CheckSpec` aceita `thresholds`; o limiar de CCN é `max_ccn`.

## Decisões (padrões adotados; o dono pediu menos perguntas)

1. Fórmula: `CRAP = CCN² · (1 − cov)³ + CCN`, `cov` em 0..1 sobre as linhas da função (`from..to`).
2. Limiar `max_crap`, padrão **30** (valor clássico), por linguagem, em `OBSERVATION` até a calibração
   do passo 9. Política `PREMISE`, como o `ComplexityCheck`.
3. Só reprova função nova ou com CRAP maior que antes, como a complexidade. O CRAP antigo exigiria
   cobertura do commit pai; **não medir**: função existente só é comparada pelo CCN antigo e pela
   cobertura atual (aproximação; registrar no ADR/relatório do passo 9).
4. Sem relatório de cobertura para o arquivo (`coverage.of(path)` é `None`) ou função sem linha
   executável (`fraction` é `None`): `cov = 0` para arquivo nunca visto (pior caso, como a nota de
   mutação "sem cobertura conta contra"); função sem linha executável usa `cov = 1` (nada a testar).
5. Cobertura que não roda: `Undecided` (`TOOL_FAILED`/`NotApplicable`), nunca aprovar em silêncio.

## Mudanças

1. **Extrair a cobertura** de `MutationCheck._coverage` para `checks\coverage.py`: função
   `async def run_coverage(tools, adapter, worktree, values) -> CoverageReport` com o mesmo
   comportamento (apaga o relatório). `MutationCheck` passa a chamá-la. Testes de mutação seguem
   verdes sem alteração.
2. **`complexity.py`**: `parse_functions` ganha variante que devolve `Function(ccn, first, last)`;
   `parse_functions` atual (usada por `measurer.py` e planner) fica igual, derivada da nova.
3. **`checks\crap.py`**: `crap(ccn, cov)` puro; `max_crap(data, language)`; `CrapCheck` com a mesma
   forma de `ComplexityCheck` (`tools, worktree, changes, files, before, lizard, adapter`),
   `gate = 8`, `requires = {"structural_meters", "coverage"}`. Finding: `target=path::função`,
   `measured=CRAP`, `limit`.
4. **`specs.py`**: `CheckSpec("crap", 8, Mode.OBSERVATION, PREMISE, thresholds={"max_crap"})`.
5. **`measurer.py::judge()`**: `CrapCheck` depois de `ComplexityCheck`. Se a cobertura foi pedida
   duas vezes (mutação e CRAP), cachear por `head` dentro do `judge` para não rodar duas vezes.
6. **UI**: `GATES` em `ui\view.py` e `GATE_NAMES` em `ui\live.py` ("crap"); atualizar
   `tests\ui\test_view.py` e `test_live.py` (nomes em ASCII).

## Testes (`tests\checks\test_crap.py`)

- `crap` puro: cov 1 → CCN; cov 0 → CCN²+CCN; valores conhecidos (CCN 5, cov 0,5 → 8,125).
- Função nova coberta, abaixo do limiar: `Approved`. Nova, descoberta, CCN alto: `Rejected`.
- Função existente que não mudou: `Approved` mesmo acima do limiar.
- Arquivo ausente do relatório → `cov = 0`. Cobertura falhando → `Inconclusive`.
- Sem arquivos de produção → `Approved`.
- Suportes (`tests\checks\support.py`, `test_pieces.py`, `test_real_run.py`): incluir `crap` em
  `CheckSettings` e na ordem do pipeline, como foi feito para `mutation`.

## Fora do escopo

Calibração do limiar (passo 9), métricas opostas (passo 8), CRAP de outras linguagens (leitores já
dão `FileCoverage`; o lizard já lê várias; só testar Python agora).

## Pronto quando

`tests\checks`, `tests\ui`, `tests\mutation` passam; ruff e mypy limpos; suíte completa em segundo
plano (~17,5 min) sem regressão.
