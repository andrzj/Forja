# Plano: paralelismo de tarefas com escopos disjuntos (fila 7, passo 6)

Fontes: Especificação, linhas 505 (“escopos disjuntos podem rodar em paralelo; as demais, em sequência”) e 542 (“paralelismo só com escopos disjuntos, decidido deterministicamente; a versão inicial é sequencial”); `docs\plano-endurecimento.md`, passo 6. Estado do código lido em 30/10/2026; só o que foi visto está dito.

## Estado lido

- `orchestrator\phases.py::_execute` percorre `children_of(Level.TASK, run)` em série e chama `TaskCycle.run(task)`; para quando `meter.exhausted()`; fecha com `CLOSING`.
- `TaskCycle.run`: entra em `IN_PROGRESS`, cria o ramo da tarefa (`create_task_branch`), trabalha cada etapa (`_stage`, uma worktree de tentativa por tentativa) e, no fim, `_integrate`: `workspace.integrate_task` (merge `--no-ff` no ramo da execução, na worktree da execução), `measurer.integration(run_worktree)` e, se o gate de integração reprova, `rollback_integration`. Conflito de merge levanta `IntegrationConflict` e a tarefa fica `BLOCKED`.
- `StopRun` (agente que não continua, falhas de infraestrutura repetidas, rede) sobe até `Orchestrator.run`, que pausa a execução com o motivo.
- Escopo: `TaskDefinitionBody.scope` é lista de caminhos do repositório; `checks\scope.py::in_scope` trata cada entrada como arquivo ou como diretório (prefixo com `/`).
- `depends_on` existe no esquema da tarefa (`core\artifacts\schemas.py`), mas **nada fora do esquema o lê**: hoje a ordem é só a do log.
- O log (`Journal`/`EventLog`) é gravado de código síncrono dentro de um único laço `asyncio`; duas tarefas concorrentes intercalam eventos, não os misturam.

## Decisões (minhas, reversíveis)

1. **Disjunção** = nenhum par (entrada de A, entrada de B) em que uma seja igual à outra ou prefixo de diretório da outra (mesma regra de `in_scope`, comparada com `/` normalizado e sem diferenciar maiúsculas, como `scope.py` já normaliza). Só o escopo de produção; o diretório de testes do autor de testes **não** entra na disjunção (o conflito de arquivo de teste comum cai no `IntegrationConflict` existente e a tarefa fica bloqueada, dito como limite).
2. **Quem pode começar** (determinístico, em função só do log e dos escopos): a tarefa T, na ordem do log, só começa se (a) cada tarefa de `depends_on` está `INTEGRATED`, e (b) seu escopo é disjunto do de toda tarefa em andamento **e** do de toda tarefa anterior a ela na ordem que ainda não está `INTEGRATED`/`BLOCKED`. (b) mantém a ordem relativa de tarefas que se tocam, como hoje. `depends_on` passa a ser lido apenas aqui, porque em paralelo a ordem do log deixa de bastar; em modo sequencial (limite 1) o comportamento é o de hoje, sem ler `depends_on`.
3. **Limite** de tarefas simultâneas: chave `paralelismo` no `execucao.toml` e `--paralelismo N` na linha de comando, padrão 1 (sequencial, idêntico a hoje), recusa valor menor que 1.
4. **Integração serializada**: um `asyncio.Lock` em volta de `_integrate` inteiro (merge, gate de integração, rollback), porque os três mexem na worktree e no ramo da execução.
5. **Parada**: se uma tarefa levanta `StopRun`, as outras são canceladas e a execução pausa; as canceladas retomam do log como numa interrupção.

## Passos (um commit cada; Plano de execução atualizado em cada um)

**6a. Disjunção e seleção.** Módulo puro `orchestrator\schedule.py`: `disjoint(a, b)` e `startable(tasks, running, done, limit)` (ordem do log, regra 2, limite 3). Testes de tabela: diretório contra arquivo dentro dele, mesmo arquivo, maiúsculas e `\`, `depends_on` não integrada, tarefa anterior que se toca ainda aberta, limite 1 igual à ordem de hoje. Ainda não ligado.

**6b. Agendador concorrente.** `phases._execute` com limite 1 segue como está (mesmo caminho de código, nenhuma mudança de comportamento); com limite maior, `asyncio.TaskGroup` com `startable`, e `Lock` na integração. **Ler antes de construir, não perguntando:** estado compartilhado que hoje assume uma tarefa por vez (`ctx.meter`, sinks e tela, cache e base do `measurer`, `CoverageShare`, nomes de worktree e de ramo, limite de processos do runner), cada um com o que muda ou o que fica declarado como limite. Opção e chave de configuração (decisão 3).

**6c. Integração e parada.** Teste com repositório real de duas tarefas disjuntas integradas em ordem de término, uma tarefa que reprova no gate de integração (rollback não pode levar junto o merge da outra: o `Lock` e o `rollback_integration` por tarefa), `StopRun` com outra em curso.

**6d. Retomada e resumo.** Retomada com duas ou mais tarefas `IN_PROGRESS`; resumo e diário com tarefas concorrentes (a ordem do resumo é a do log, não a de término); `forja` mostra mais de uma tarefa em andamento, ou declara que mostra a primeira.

Fecho: gate de mutação (`scripts\mutate.py`) nos arquivos novos; documentação de uso e ADR no passo 7 da fila.

## Fora de escopo

Escopos que se tocam em paralelo; reordenar tarefas; E2E real (do dono); paralelismo dentro de uma tarefa (etapas).
