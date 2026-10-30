# Plano: endurecimento (incremento 7)

Item 7 da fila. Fontes: Especificação (linhas 56, 440, 505, 542, 655, incremento 7 do Plano). Estado do código lido no passo 0 (30/10/2026); só o que foi visto está dito.

## Divergência apontada (regra 7 do Plano)

O incremento 7 do Plano lista “prevenção de suspensão”; a linha da fila 7 não a lista. Vale a Especificação (linha 655): entra aqui (passo 2).

## Estado lido no passo 0

- **Paralelismo:** não existe. `orchestrator\phases.py::_execute` percorre as tarefas em série (`await cycle.run(task)`). Falta detecção de escopos disjuntos, worktree por tarefa, agendador concorrente e serialização da integração. O git já serializa operações por mutex (Especificação, linha 543).
- **Mutação incremental:** `checks\mutation.py` já muta só as linhas adicionadas. Existem `LanguageCapability.MUTATION_INCREMENTAL` e `OperationRequest.incremental` / `changed_files` (`core\adapters\language.py`), mas nenhum adaptador declara a capacidade e o check não a consome. `scripts\mutate.py` (gate da própria Forja) muta por arquivo.
- **Suspensão:** não implementada (nenhum `SetThreadExecutionState` no código).
- **Modo CI:** `--config` existe e já dispensa a confirmação final e a pergunta de execução pendente (recusa em vez de perguntar). Ainda perguntam: `choose_cli` com várias instalações da mesma CLI, o menu do objetivo quando o `execucao.toml` não traz verbo, e o nome do projeto em `criar` (`console.ask` sem checar interatividade).
- **Adaptador genérico:** não existe. Registro fixo `KNOWN_CLIS` em `executors\__init__.py`.
- **Promoção de gate:** o mecanismo existe. `[checks.<id>] mode = "blocking"` exige `promotion = { date, reason }` e `on_inconclusive`; entra no digest da política. Falta só a decisão com dado.
- **CLIs por papel:** só implementador (`--cli`) e autor de testes (`--cli-testes`, só em `corrigir`) têm escolha própria; os demais papéis usam a do implementador. Nenhuma sugestão de CLIs diferentes.

## Passos

Um passo por commit; Plano atualizado no mesmo commit.

**1. Modo CI sem pergunta.** Com `--config` (ou sem terminal), nenhuma pergunta: `choose_cli` com várias instalações recusa e diz que `executavel` no `execucao.toml` resolve; objetivo ausente recusa; nome do projeto em `criar` vem do `execucao.toml` ou, como na preparação interativa, do nome do diretório. Teste: cada caso recusa com a mensagem certa sem ler o terminal. Doc: `execucao.toml` completo para CI.

**2. Prevenção de suspensão.** `SetThreadExecutionState` (`ctypes`, `kernel32`) ligado no início da execução e liberado no fim, inclusive em erro; fora do Windows, sem efeito e sem aviso falso. Teste com a chamada substituída. Limite a declarar: só Windows.

**3. Sugestão de CLIs diferentes entre papéis.** Na preparação, se há mais de uma CLI instalada e o dono escolheu só uma, a Forja sugere uma segunda para o autor de testes (diversidade de autor). Só sugestão no texto; não muda escolha.

**4. Adaptador genérico de CLI.** Adaptador de executor configurado por modelo de comando no `execucao.toml` ou na configuração do usuário (comando, argumentos com marcadores para pacote, modelo e diretório; leitura da saída como texto final). Lê o `ExecutorAdapter` e o `KNOWN_CLIS` antes; o que a CLI não declara (permissões por papel, eventos) o adaptador diz que não oferece, e a Forja declara o limite no resumo. **Dúvida a resolver lendo o código, não perguntando:** o contrato mínimo de `ExecutorAdapter`.

**5. Mutação incremental nos adaptadores.** Declarar `MUTATION_INCREMENTAL` onde o mutator da Forja já permite (mutação restrita a arquivos e linhas mudadas) e fazer o `MutationCheck` consumi-la. Sem a capacidade, o comportamento de hoje não muda. O gate de mutação da própria Forja (`scripts\mutate.py`) fica como está.

**6. Paralelismo de tarefas com escopos disjuntos.** O maior passo, em subpassos próprios, cada um com plano curto antes: (a) decisão determinística de disjunção a partir de `Task.scope`; (b) agendador concorrente com limite de tarefas simultâneas e padrão 1 (sequencial, como hoje); (c) integração serializada na branch da execução; (d) retomada e resumo com tarefas concorrentes. Ordem e dependências entre tarefas seguem como estão. Gate de mutação nos arquivos novos.

**7. Documentação de uso.** `docs\` do usuário: modo CI, CLIs por papel e a sugestão, adaptador genérico, mutação incremental, paralelismo, suspensão. ADR para o que for decisão (paralelismo e adaptador genérico, pelo menos).

**8. Promoção de gates e calibração (C2). Parado.** Depende de relatórios de `forja revisao` de execuções reais, do dono (`docs\limiares.md`). Quando houver: calibrar, e promover por `promotion` na política com data e motivo. A Forja não promove nem calibra sem esse dado.

## Fora de escopo

E2E real (do dono); mudar limiar sem dado; paralelismo com escopos que se tocam; item 8 da fila.
