# 0015. Git em memória para testar o orquestrador

- Status: Aceito
- Data: 11/10/2026

## Contexto

A mutação do orquestrador e dos módulos novos era impraticável: cada mutante em `task_cycle` ou `phases` reexecuta os testes que passam por ele, e esses eram os cerca de 50 testes de ponta a ponta que sobem um repositório git, worktrees e um subprocesso como agente (1,5 a 2,5 s cada, ~75 s por mutante). A medição da suíte rápida (2237 testes, 117 s) mostrou que o custo vinha de git e processos reais, não de esperas: relógio, `sleep` e `fsync` já eram injetáveis.

## Decisão

- **`forja.testing` faz parte do pacote.** `MemoryRepo` (commits, branches, trailers, três vias por arquivo) e `MemoryWorkspace` (a porta `Workspace` sobre ele) ficam em `src/forja/testing/`, para que quem integrar um adaptador, um medidor ou um workspace teste contra os mesmos dublês que a Forja usa em si. Os worktrees continuam sendo diretórios de verdade; o que está em memória é o histórico.
- **O dublê não pode se afastar do git.** `tests/orchestrator/test_workspace_contract.py` roda os mesmos cenários (rodada, tarefa, commit com trailers, integração, conflito, rollback, remoção, vigilância de refs, veredito de cada operação aberta) contra `MemoryWorkspace` e `GitWorkspace`, com as mesmas expectativas.
- **A porta `Workspace` devolve um `Watch`**, protocolo estrutural, em vez do `GitWatch` concreto.
- **Dois níveis de teste do orquestrador.** `MemoryWorld` (git em memória, agente em processo) para a lógica; `World` (git real) só para o que é sobre git: `test_workspace_git`, `test_phases_git` e a metade `git` do contrato. Os módulos de git real levam a marca `integration`.
- **`FORJA_FAST=1` deixa de fora o que é `integration`.** A mutação de `orchestrator/` (exceto `workspace_git`), `checks/`, `languages/` e `testing/` roda assim; a de `workspace_git` e a de `core/` continuam com a suíte inteira.
- **O agente falso roda em processo por padrão** e emite os mesmos eventos de intenção e efeito de um processo; com `in_process=False` (ou `pause`), começa um processo de verdade, como os testes de corte e morte exigem.
- **`pytest-xdist` entra como dependência de desenvolvimento.** Para a suíte ser segura em paralelo, `GitWorkspace` recebe `git_running` injetável (a checagem de processo git da máquina inteira fazia o teste de recuperação de lock falhar sob concorrência).

## Consequências

- O orquestrador tem 124 testes rápidos que rodam em ~5 s (antes ~110 s); a suíte completa sem `slow` fica em ~100 s no Windows com `-n auto`.
- Quem muda `GitWorkspace` precisa manter o contrato verde nos dois lados, o que também documenta o comportamento esperado.
- O dublê guarda só texto. Binários, permissões e links ficam de fora e são cobertos pelos testes de git real.
- A seleção de testes por arquivo alterado, o cache da base e o tempo por gate no resumo (ganhos do mesmo tipo para os repositórios-alvo) ficam para um incremento próprio.
