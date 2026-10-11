# 0014. Os gates leem o diff da tentativa e comparam com o commit pai

- Status: Aceito
- Data: 11/10/2026

## Contexto

A catraca de lint e o gate de complexidade precisam saber o que era violação antes da tentativa. A base da execução muda a cada tarefa integrada, então comparar com a medição do começo da execução misturaria o trabalho de tarefas anteriores com o da tentativa. Além disso, o agente trabalha numa cópia e o resultado volta para o worktree da tentativa; o que os gates medem precisa ser o que será commitado, e nada que o `git add` deixe de fora.

## Decisão

- **O "antes" é o commit pai da tentativa.** O medidor lê as mudanças com `git add -A` seguido de `git diff --cached -M HEAD` (estado, número de linhas e patch) e reconstrói o texto anterior dos arquivos alterados com `git show HEAD:<caminho antigo>`. Lint e complexidade rodam sobre essa cópia e sobre o worktree. Renomeações contam como o mesmo arquivo; arquivo novo parte de zero.
- **A catraca de lint é por (arquivo, regra).** Reprova quando a contagem de alguma dupla aumenta. Mudar linhas de lugar não faz violação antiga parecer nova. O ruff roda com `--ignore-noqa`, e comentários que desligam ferramenta (`noqa`, `fmt:`, `gitleaks:allow`, `lizard forgives` e parentes) reprovam o escopo.
- **Complexidade reprova só o que ficou pior.** Função acima do limite (15 por padrão, ajustável por linguagem na política) reprova se for nova ou se piorou. Débito antigo é tarefa do planejador.
- **Testes são comparados com a base.** A primeira medição guarda em `base.json` os testes instáveis (resultado diferente entre duas rodadas) e os que passaram nas duas. Instável não reprova. Teste que passava na base e agora sumiu, foi pulado ou falha reprova; os testes ficam congelados no escopo, então sumir é sinal de trapaça, não de refatoração.
- **Segredos: só linhas adicionadas.** O patch sem contexto vira texto (só as linhas `+`, lidas seguindo as contagens dos `@@`, de modo que uma linha adicionada que pareça cabeçalho continue sendo linha adicionada) e o `gitleaks stdin` o lê. O código de saída de vazamento é 2 (`--exit-code 2`), porque o gitleaks usa 1 tanto para vazamento quanto para erro. O achado traz a regra e o lugar, nunca o valor. Sem o binário, o resultado é inconclusivo e bloqueia a tarefa.
- **Arquivos que o git ignora não passam.** Um arquivo ignorado dentro do worktree seria visto pelo build e pelos testes mas não iria para o commit. Só caches de ferramenta são tolerados; um `.pyc` fora de `__pycache__` é módulo importável sem fonte e reprova.
- **Pytest é lido pelo texto (`-rA`), não por `--junitxml`.** O contrato do adaptador exige planos que não dependem de diretório de saída, e o relatório em arquivo deixaria resíduo. O parser trata saída que não fecha (código de saída e linhas que se contradizem) como não analisável, o que torna o gate inconclusivo em vez de aprovado.

## Consequências

- Cada tentativa mede o commit pai, então o custo do lint e da complexidade cresce com os arquivos alterados, não com o repositório.
- A comparação com a base de testes depende do `base.json` da primeira medição; sem ele, nenhum teste é cobrado como presente (e o instável não existe).
- O que o gitleaks real aceita foi confirmado só pela documentação; o binário não estava instalado quando o código foi escrito, e os testes usam um falso que segue essa documentação. Há um teste marcado para rodar com o binário real quando houver um.
- Pytest precisa rodar no ambiente do repositório; quem prepara esse ambiente é o isolamento (incremento 1e).

Ver a especificação, seções "Ciclo por tarefa e gates" e "Regras para linters e formatadores".
