# Plano do passo 8 do 3b: métricas opostas (`PassThroughCheck`, `ModuleDepthCheck`)

Contexto: a Especificação (linhas 17, 78, 292, 354, 408-409) pede que reduzir complexidade não crie
módulos rasos nem métodos *pass-through*. Os dois medidores leem a árvore sintática (tree-sitter),
fazem parte do gate 8 e nascem em `OBSERVATION` (a definição varia por estilo e linguagem, risco de
falso positivo). Antes de virarem bloqueantes: validação contra referência e exemplos (passo 9).

## Decisões (dono: o produto cobre Python, Go, Java, C#, JavaScript e TypeScript; nada de entrega parcial)

1. **Todas as linguagens agora**, com tree-sitter (`tree-sitter` 0.26 e as gramáticas de Python, Go,
   Java, C#, JavaScript e TypeScript/TSX, acrescentadas ao `pyproject.toml`). Um leitor por família
   em `checks\structure\` (`python`, `go`, `java`, `csharp`, `script` para JS/TS); só os nomes dos nós
   mudam. A linguagem sai do sufixo do arquivo, não do adaptador, então o check serve a qualquer
   adaptador que classifique arquivos como produção.
2. **Catraca**, como complexidade e CRAP: só reprova função/módulo novo ou que piorou em relação ao
   commit pai. Dívida antiga não reprova.
3. **Pass-through** = função ou método cujo corpo (sem docstring) é uma única chamada (`return f(...)`
   ou `f(...)`) com exatamente os parâmetros da própria função, na mesma ordem, e nada mais (`*args`,
   `**kw`, `...rest`, `xs...` contam como repasse do mesmo nome). Não contam: dunders e funções
   decoradas (Python), métodos de `Protocol`, construtores (Java, C#, JS/TS), métodos sem corpo
   (abstratos, interfaces). Anotações de Java/C# não isentam.
4. **Profundidade de módulo** = superfície pública ÷ implementação. Superfície = 1 por nome público +
   1 por parâmetro (classe: 1 + seus métodos públicos e o construtor). "Público": Python sem `_`
   inicial (ou `__all__`); Go com inicial maiúscula; Java/C# `public` (membros de interface são
   públicos); JS/TS `export` (membros `private`/`protected`/`#`/`_` não). Implementação = nº de
   instruções (`*_statement` mais declarações), sem imports.
5. **Reprova** módulo com razão acima de `max_interface_ratio` (padrão **1,0**) e ao menos
   `min_statements` instruções (padrão **10**) que seja novo ou tenha razão maior que a do commit pai.
   Os dois números são políticas por linguagem; chute até a calibração do passo 9.
6. Arquivo que não parseia: `Inconclusive` (`UNSUPPORTED_CONSTRUCT`), nunca aprovar em silêncio. Texto
   do commit pai que não parseia: sem comparação (tratado como arquivo novo).

## Limitações conhecidas (registrar no passo 9)

- JS em CommonJS (`module.exports`) não tem `export`: superfície 0, o módulo nunca reprova.
- Go: só funções, métodos e tipos exportados no topo; constantes e variáveis não entram.
- C#: propriedades não entram na superfície; `global_statement` (top-level programs) não é contado duas vezes.
- Os limiares valem para todas as linguagens igual até haver dados.

## Mudanças

1. `checks\structure\` (`nodes.py`, `python.py`, `go.py`, `java.py`, `csharp.py`, `script.py`,
   `__init__.py` com `analyze(path, texto) -> Module | None`).
2. `checks\shape.py` (leitura e política compartilhadas), `checks\pass_through.py`,
   `checks\module_depth.py`.
3. `checks\specs.py`: `pass_through` e `module_depth` (gate 8, `OBSERVATION`, `PREMISE`; thresholds
   `max_interface_ratio`, `min_statements`).
4. `orchestrator\measurer.py::judge()`: os dois checks depois do `CrapCheck`; o texto do commit pai
   é lido com todos os sufixos das linguagens lidas (`SUFFIXES`), não só `.py`.
5. UI: gates `pass_through` ("pass.") e `module_depth` ("prof.") em `ui\view.py::GATES` e
   `ui\live.py::GATE_NAMES`; os rótulos curtos mantêm a linha do status em 120 colunas.
6. Testes: `tests\checks\test_structure.py` (leitores das 6 linguagens), `test_pass_through.py`,
   `test_module_depth.py`; ordem do pipeline atualizada nos testes existentes.

## Fora do escopo

Calibração dos números e validação contra referência (passo 9); grafo de dependências, métricas de
pacote e acoplamento de mudança (Especificação 410-411); os adaptadores de Go/Java/C#/JS/TS em si
(incremento 5), que só precisam classificar arquivos como produção para estes checks funcionarem.

## Pronto quando

`tests\checks` e `tests\ui` passam; ruff e mypy limpos; suíte completa em segundo plano sem regressão.
