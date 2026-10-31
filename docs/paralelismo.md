# Paralelismo de tarefas

Por padrão a Forja roda uma tarefa de cada vez, na ordem do log. Com `paralelismo` acima de 1, ela pode rodar tarefas juntas, desde que os escopos delas não se toquem.

> **Limite de segurança: não use `paralelismo` acima de 1.**
> Com mais de uma tarefa em andamento, a guarda de git que confere o que o agente mudou ignora, pelo nome, o trabalho da Forja nas outras tarefas. Um agente que mexa no ramo da execução, no ramo de outra tarefa ou na worktree de outra tarefa não é visto e não é reprovado. A correção completa está pendente (ver [Limite de segurança: a guarda de git](#limite-de-segurança-a-guarda-de-git)). Até ela existir, mantenha `paralelismo = 1`.

## Configuração

```toml
paralelismo = 2
```

No `execucao.toml`, chave `paralelismo`. O padrão é 1, que é sequencial e igual ao comportamento anterior. O mínimo é 1. Não há opção de linha de comando para isso. O valor vai para o log da execução, e a retomada usa o valor gravado.

## Quando duas tarefas são disjuntas

Duas tarefas são disjuntas quando nenhuma entrada do escopo de uma é igual à da outra, nem está dentro de um diretório listado pela outra. A comparação normaliza os caminhos:

- `\` vale como `/`;
- maiúsculas e minúsculas não contam;
- espaço e ponto no fim de cada parte do caminho são ignorados, como o Windows trata esses nomes;
- barra no fim é ignorada.

| Escopo A | Escopo B | Disjuntos? |
| --- | --- | --- |
| `src/app` | `src/lib` | sim |
| `src/app` | `src/app/util.py` | não: `util.py` está dentro de `src/app` |
| `Src/App` | `src/app/` | não: é o mesmo caminho depois da normalização |

A regra vale só para o escopo de produção que a tarefa declara. O diretório de testes do autor de testes fica fora dela. Se duas tarefas mexem no mesmo arquivo de teste, o conflito aparece na integração (ver abaixo).

## Quem pode começar

A decisão é `orchestrator\schedule.py::startable`, uma função pura. Ela percorre as tarefas na ordem do log:

- tarefa integrada ou bloqueada não entra na conta;
- uma tarefa aberta começa só se couber no limite, se o escopo dela for disjunto de cada tarefa aberta que vem antes na ordem do log (em andamento, esperando ou que vai rodar), e se todas as tarefas de `depends_on` já estiverem integradas.

Com limite 1, só a primeira tarefa aberta pode começar, e `depends_on` não é lido. É o comportamento de antes.

`depends_on` é lido do payload da tarefa, mas o planejador não o preenche: hoje a lista é sempre vazia. A condição de dependências não bloqueia nenhuma tarefa até o planejador passar a produzi-la.

Tarefa bloqueada fecha, mas quem depende dela nunca começa. Se nenhuma tarefa está em andamento e nenhuma pode começar, a fase de execução termina e as tarefas que sobraram ficam abertas. Com o orçamento esgotado, não começa tarefa nova; as que estão em curso terminam.

## Integração

Merge, gate de integração e rollback rodam um de cada vez, sob um `Lock`, porque os três mexem na worktree e no ramo da execução. A ordem de integração é a de término de cada tarefa.

**Conflito de merge.** Quando duas tarefas alteram o mesmo arquivo de forma incompatível, o merge falha, a Forja desfaz o merge e levanta `IntegrationConflict` (`orchestrator\workspace_git.py`). `TaskCycle._integrate_alone` (`orchestrator\task_cycle.py`) captura a exceção: a tarefa vira `BLOCKED` com `reason` `integration_conflict` e o texto do conflito em `detail`, a worktree da execução fica como estava antes do merge, e as outras tarefas seguem, com `paralelismo` 1 ou acima. A tarefa bloqueada precisa de revisão do dono; a Forja não tenta o merge de novo. (Antes do item 9 da fila, a exceção não era capturada e derrubava a execução; já não é assim.)

## Parada

Quando uma tarefa levanta `StopRun` (o agente não pode continuar, falhas de infraestrutura seguidas, rede que não volta) ou quando qualquer erro escapa de uma tarefa, a Forja cancela as outras tarefas em curso e pausa a execução. Na retomada, as tarefas que estavam em andamento voltam juntas, a partir do log.

## Resumo, diário e tela

- O resumo e o diário listam as tarefas na ordem do log, não na de término.
- A tela mostra a primeira tarefa em andamento. A barra viva diz `+N em andamento`; o modo simples acrescenta `(+N em andamento)` à linha da tarefa.
- O contador "tarefa N/M" e o feed de atividade do agente são da tarefa que está na tela.
- Os tokens somam todas as tarefas, porque o orçamento é da execução.
- Uma tentativa descartada de outra tarefa não entra na lista de rejeições da tela.

## Limite de segurança: a guarda de git

A guarda confere, durante a chamada ao agente, se o git mudou fora da tentativa. Com `paralelismo = 1`, ela é a de sempre: qualquer mudança externa reprova.

Com mais de uma tarefa, `orchestrator\workspace_git.py::others_work` deixa de contar como mudança do agente o trabalho da Forja nas outras tarefas da execução, identificado **pelo nome**:

- refs: o ramo da execução e os ramos `forja/<execução>/<tarefa>` das outras tarefas da execução (um ramo com outro nome, como `forja/<execução>/t9` sem uma tarefa `t9`, continua vigiado);
- árvores: qualquer caminho dentro da pasta de worktrees da execução, exceto a worktree da própria tentativa. Isso inclui a worktree de outra tarefa e a do ramo da execução.

Continuam vigiados: o ramo e a worktree da própria tarefa, refs de fora da execução, a configuração e os hooks.

**Consequência.** Um agente que mexa no ramo da execução, no ramo de outra tarefa ou na worktree de outra tarefa não é visto. Não há reprovação por isso.

**Correção pendente.** A guarda deve passar a conferir a mudança exata: a Forja registra cada `(ref, antes, depois)` em cada operação do workspace e a guarda confere esses valores. Isso muda todas as operações do workspace. Fica para antes de liberar `paralelismo` acima de 1.

## Fora de escopo

- Escopos que se tocam rodando em paralelo.
- Reordenar tarefas.
- Paralelismo dentro de uma tarefa (entre etapas).

A decisão está em [ADR 0032](adr/0032-o-paralelismo-usa-escopos-disjuntos-e-a-guarda-de-git-ignora-por-nome.md).
