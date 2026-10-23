# Plano: gate 9, arquitetura

Estado: plano, nada implementado; sem perguntas abertas. Regra do dono: gates grandes só com plano escrito antes. Vem depois do plano do gate 6 e antes de sua construção.

## O que a Especificação diz

- Tabela de gates, linha 9: reprova quando há **ciclo de dependência novo; violação de regra de camada; piora nas métricas de pacote**.
- "Medidores próprios": **grafo de dependências entre módulos via imports: ciclos, instabilidade, abstração e distância da sequência principal (métricas de pacote de Robert C. Martin), conformidade de camadas**. Em "Ferramentas": medidor feito com tree-sitter.
- "Modelo arquitetural global": a medição de base extrai o grafo; ele é restrição para toda tarefa; um diff que cria ciclo, viola camada ou aumenta acoplamento é rejeitado mesmo que as métricas locais melhorem. "Mudanças arquiteturais detectadas disparam ADR" (gate 14 e documentador: fora deste plano).
- "Medidores próprios", última frase: **toda ferramenta escrita internamente é validada contra uma ferramenta de referência num repositório conhecido antes de virar gate.**
- Plano de execução, incremento 5: "modelo arquitetural global (grafo, ciclos, métricas de pacote, camadas)"; pronto quando "uma refatoração que cria ciclo de dependência é rejeitada".
- Regras gerais: check novo nasce em observação; ferramenta que falha é `Inconclusive`; o que o usuário deve fornecer e não forneceu **não executa e o resumo diz** (ADR 0024); catraca, não faxina (só o que é novo reprova).
- A Especificação **não diz onde se declaram as regras de camada** nem como se mede a abstração em cada linguagem: decididos abaixo.

## O que o código tem hoje (lido em 23/10)

- Nenhum código de grafo, ciclo ou métrica de pacote.
- `checks\structure\` lê cada arquivo com tree-sitter nas seis linguagens (`DIALECTS`, `dialect_of`, `analyze(path, texto) -> Module`; `SyntaxProblem` quando não parseia); `Module` só traz `forwarders`, `interface` e `statements`. `checks\shape.py` e `checks\module_depth.py` são o molde de check por texto (compara com o texto do commit pai, `Inconclusive(UNSUPPORTED_CONSTRUCT)` quando não parseia).
- `PipelineMeasurer.judge` já lê o commit pai dos arquivos mudados (`read_before`) e conhece os projetos (`_active`, `ScopedAdapter`, `owner_of`); `baseline()` devolve `Baseline(ok, problems, metrics)`.
- A política já tem o molde de seção com lista do usuário, soma entre camadas, fora do digest quando vazia e congelada em `policy.json` (`[licenses] forbidden`, `EffectivePolicy.forbidden_licenses`).

## Decisões

1. **Três checks, no gate 9:** `dependency_cycles`, `layer_rules` e `package_metrics`. Os três nascem em `Mode.OBSERVATION`; política para "não consegui medir": `BLOCK` nos dois primeiros, `PREMISE` em `package_metrics` (os limiares são palpite até a calibração).
2. **Unidade = diretório.** Nó do grafo é o diretório do arquivo de produção, relativo ao `base` do projeto (monorepo: um grafo por projeto, sem aresta entre projetos). Razão: em Go o diretório é o pacote, em Java e C# o pacote/namespace segue o diretório por convenção, em Python é o pacote, em JS/TS é a pasta; e em Java, C# e Go a referência dentro do mesmo pacote não passa por `import`, então ciclo entre arquivos seria incompleto. Arquivo de teste, fixture e documentação ficam fora (a classificação é do adaptador).
3. **Arestas = imports que resolvem para outro diretório do mesmo projeto.** Leitores novos em `checks\structure\` (um por dialeto, mesmo molde: `imports(root) -> tuple[str, ...]`, texto bruto do alvo). O resolvedor por linguagem, em `checks\architecture\`:
   - Python: absoluto e relativo, pelo caminho do módulo contra os arquivos do projeto (maior prefixo que existe);
   - Go: caminho do `import` com o prefixo do `module` do `go.mod` do `base`;
   - Java: `import a.b.C;` contra o `package` declarado em cada arquivo mais o nome da classe; `import a.b.*;` contra o pacote;
   - C#: `using Ns;` contra os `namespace` declarados;
   - JS/TS: só especificador relativo (`./`, `../`), com as extensões e `index`; especificador sem ponto é externo. **Limite declarado:** `paths` do `tsconfig` e aliases de bundler não são resolvidos.
   Import que não resolve é externo e fica fora. Import dentro de função, `require` dinâmico e reflexão não são vistos.
4. **Ciclo = componente fortemente conexo (Tarjan) com mais de um diretório.** Reprova se algum componente do estado novo **não cabe em nenhum componente do estado antigo** (ciclo novo, ou ciclo antigo que ganhou um diretório). Ciclo antigo que continua igual ou encolhe não reprova (catraca). A mensagem traz o caminho do ciclo.
5. **Camadas: seção `[architecture]` do `forja.toml`**, lista ordenada de cima para baixo: `layers = [{ name = "cli", paths = ["src/forja/cli"] }, …]`. Uma camada pode depender de si mesma e das de baixo; aresta para camada **acima** é violação. Diretório que não pertence a nenhuma camada fica livre. Reprova só a **aresta nova** que viola (catraca). Soma entre camadas de configuração, valida (nome único, caminho relativo sem `..`), vai ao digest só quando existe e é congelada em `policy.json`, como `[licenses]`. Sem camadas: `layer_rules` é `NotApplicable("architecture_layers")` e os resumos dizem em destaque **"Camadas NÃO verificadas: sem regras em [architecture]"** (mesmo tratamento do SAST sem regras, ADR 0024). A Forja não deduz camadas.
6. **Métricas de pacote (Martin), por diretório:** `Ca` (diretórios que o importam), `Ce` (que ele importa), `I = Ce / (Ca + Ce)` (0 se ambos 0), `A = tipos abstratos / tipos`, `D = |A + I − 1|`. Tipo abstrato por linguagem: Python, classe que herda de `ABC` ou `Protocol`, ou com `@abstractmethod`; Go, `interface`; Java e C#, `interface` e classe `abstract`; TS/JS, `interface` e classe `abstract` (JS puro não tem: `A = 0`). Reprova um diretório **tocado** pela tentativa quando `D` passa do limite e **cresceu** em relação ao estado antigo (ou o diretório é novo). Limites por linguagem na política: `max_distance` (palpite inicial 0,8, até a calibração, como nos outros checks de forma) e `min_types` (diretório com menos tipos que isso é ignorado, 3). Todo o resto (`Ca`, `Ce`, `I`, `A`) é evidência, não critério.
7. **Estado antigo sem copiar a worktree.** Os leitores trabalham sobre texto, então o grafo antigo sai dos textos do commit pai: arquivos não mudados lidos do disco, mudados por `read_before`, adicionados ausentes. Cada texto distinto é analisado uma vez (memo por caminho e hash); a resolução é refeita nos dois estados, pois depende do conjunto de arquivos.
8. **Quando roda.** Só se a tentativa muda arquivo de produção de linguagem lida; senão `Approved`. Arquivo mudado que não parseia: `Inconclusive` (`UNSUPPORTED_CONSTRUCT`, como `module_depth`); arquivo **não mudado** que não parseia fica fora dos dois grafos. `go.mod` ilegível ou `base` sem arquivos: `Inconclusive`.
9. **Linha de base.** `baseline()` acrescenta às `metrics` o que o grafo do commit base já tem: número de ciclos, de arestas e `D` máximo por projeto, para o resumo mostrar o "antes". Não reprova nada (catraca).
10. **Validação contra referência (regra da Especificação).** Passo 0 escolhe e mede, por linguagem, uma ferramenta de referência num repositório conhecido e compara o grafo de diretórios e o `Ca`/`Ce`: `go list -f '{{.ImportPath}} {{.Imports}}'` (Go), `jdeps` (Java), `dependency-cruiser` ou `madge` (JS/TS), `import-linter`/`grimp` (Python); C# sem ferramenta equivalente decidida no passo 0 (alternativa: grafo de referências de projeto do `dotnet`, ou contagem manual de um repositório pequeno, dita no plano revisado). Divergência vira correção do resolvedor ou limite declarado.
11. **Não faz parte:** ADR disparado por mudança arquitetural (gate 14); tarefas de planejamento por violação de arquitetura; acoplamento de mudança e churn; dedução de camadas; aresta entre projetos do monorepo; resolução de `paths`/aliases de TS; ciclo entre arquivos dentro de um diretório.

## Passos (um commit cada)

0. **Ler e medir:** documentação das ferramentas de referência; instalar fora do repositório e do PATH, com permissão do dono, as que faltarem; rodar sobre repositórios descartáveis no scratchpad e sobre a própria Forja (Python); fixar a referência de cada linguagem e corrigir este plano com o que divergir.
1. **Leitores de import** nos dialetos (`checks\structure\`): campo novo em `Module` ou função `imports` à parte (decidir lendo o uso de `Module`); testes por linguagem com textos curtos, inclusive `import` em função e relativo.
2. **Grafo e resolvedores** (`checks\architecture\graph.py`, um módulo por linguagem para resolver): construção por projeto, diretórios, arestas, Tarjan, `Ca`/`Ce`/`I`/`A`/`D`. Testes com árvores de arquivos em memória e comparação com a referência do passo 0.
3. **`DependencyCyclesCheck`** e `CheckSpec("dependency_cycles", 9, OBSERVATION, BLOCK)`; testes (ciclo novo reprova, ciclo antigo igual aprova, ciclo antigo que cresce reprova, não parseia, sem arquivo de produção).
4. **Política `[architecture]`** (leitura, validação, soma, digest, `policy.json`, retomada) e **`LayerRulesCheck`** com `CheckSpec("layer_rules", 9, OBSERVATION, BLOCK)`; aviso `NO_LAYERS` em `cli\security_notes.py` ou arquivo irmão, no resumo da preparação e da entrega.
5. **`PackageMetricsCheck`** com `CheckSpec("package_metrics", 9, OBSERVATION, PREMISE, thresholds={"max_distance","min_types"})`; testes de `A` por linguagem.
6. **Integração:** os três no `PipelineMeasurer.judge` (depois de `module_depth`, antes do gate 10; ordem do pipeline atualizada nos testes que a listam), `baseline().metrics`, nomes curtos dos gates na UI (`ui\view.py::GATES`, `ui\live.py::GATE_NAMES`), projetos do monorepo.
7. **Documentação do usuário e ADR:** como declarar camadas, o que conta como aresta e o que não conta, as métricas e seus limiares, limites de resolução por linguagem. ADR (unidade = diretório; camadas declaradas pelo usuário, nunca deduzidas).
8. **Ponta a ponta real** (regra do dono: só no fecho do gate) e **gate de mutação no WSL** nos arquivos novos. E2E por linguagem: refatoração que cria ciclo é rejeitada (critério do incremento 5); aresta para camada de cima reprova; sem camadas o aviso aparece.

## Limites já conhecidos

- Sem camadas declaradas, o gate de camadas não executa (e diz).
- O grafo vê só o que o `import` declara e que o resolvedor acha; o que a referência do passo 0 mostrar a mais ou a menos entra aqui como limite por linguagem.
- Os limiares de `package_metrics` são palpite até a calibração; o check fica em observação.
- Unidade em diretório não vê ciclo entre arquivos do mesmo diretório.
