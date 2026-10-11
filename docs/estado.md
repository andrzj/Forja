# Forja — estado do incremento 0

Nota de retomada. Escrita em 10/10/2026, depois de concluídos os contratos 1 a 5, os adaptadores, o lock e a redação do pacote. A especificação (`Especificação.md`) e o plano (`Plano de execução.md`) continuam sendo a referência; este arquivo registra o que foi decidido durante a construção e que não está no código nem na spec.

## Onde estamos

O incremento 0 (fundação) está quase completo. Há 1.771 testes passando e 5 pulados, com `ruff` e `mypy --strict` limpos. Tudo foi executado apenas no Windows.

**Falta para fechar o incremento 0:**

1. ~~Teste de retomada ponta a ponta~~ — feito, em `tests/e2e/` (ver "Retomada").
2. `mutmut`: meta de 100% de mutantes mortos nos módulos de contrato; piloto feito (ver "Mutação"). Falta o resto do escopo.
3. ~~README e ADRs~~ — feitos (`README.md` e `docs/adr/`).
4. ~~Atualizar a especificação~~ — feito.

## Como trabalhar

Os comandos, as convenções e o mapa dos módulos estão no [README](../README.md). Os valores de estado persistidos estão na tabela abaixo. As decisões em forma de registro estão em [docs/adr](adr/README.md).

## Incremento 1 (em andamento)

Pedaços combinados: 1a orquestrador, 1b Python e gates, 1c gestor de git, 1d executor real, 1e isolamento, 1f preparação e CLI, 1g interface, 1h aceitação. As 16 respostas da conversa de planejamento valem para todos; as perguntas 3, 4, 5 e 7 (Claude Code instalado, restrições do WSL, quem instala as ferramentas, limite de gasto) seguem abertas e só travam o 1d e o 1e.

- **1a, bloco 1 (feito):** `forja/orchestrator/` com `config.py` (`RunConfig`, orçamento padrão, config dentro do evento de confirmação), `budget.py` (consumo lido dos eventos, `Meter`, tentativas de qualidade e falhas de infraestrutura seguidas), `operations.py` (`Journal`: `enter` e `operate` que não repetem o que o log já mostra, `Step`, ids com sufixo de `redo`) e `outcome.py` (códigos de saída 0, 1, 2, 3 e 130).
- **1a, bloco 2 (feito, mutação incompleta):** `workspace_git.py` (`GitWorkspace`: branch e worktree da execução, commit `style:`, branch da tarefa, worktree da tentativa sobre a própria branch da tarefa, commit com trailers, merge `--no-ff`, rollback, remoção, reconciliação, recuperação, fotografia) e `ports.py` (só o `Workspace` por enquanto). `Step.payload` agora é assíncrono. Último `mutmut`: 489 mortos, 2 sobreviventes e ~55 `timeout` por refazer isolados (`mutmut run <nome>`), sobretudo em `integrate_task` e `reconcile`; falta conferir esses e matar os 2 sobreviventes.
- **1a, bloco 3 (feito, mutação por rodar):** `ports.py` (os quatro `Protocol`, `RunContext`, `RejectedWork`), `task_cycle.py` (a tarefa, da branch à integração, com rejeição, bloqueio por gate inconclusivo, falhas de infraestrutura, gate de integração e rollback), `phases.py` (`Orchestrator.run`, `confirm_run`; confirmada, preparação, base, plano, execução e fechamento; pausa e saída de pausa), `summary.py` (`resumo.md` em português e o artefato). `RunConfig` ganhou `base_commit`; `RunState.previous_state` é novo. 28 testes de ponta a ponta com git e processos reais e só o julgamento roteirizado (`tests/orchestrator/fakes.py`).
- **1a, retomada ponta a ponta (feito):** `tests/orchestrator/test_resume_end_to_end.py` (102 casos, ~10 min, marcador `slow`) corta a execução real após cada linha do log (limpo e com linha cortada pela metade), mata o processo de verdade em 4 pontos e confirma que a retomada termina igual à execução sem corte (ou com um attempt descartado a mais quando o agente estava rodando). Substituiu `tests/e2e/`. Achou e corrigiu um defeito: corte entre o attempt `COMMITTED` e o stage `COMMITTED` abria um terceiro attempt.
- **Falta no 1a:** mutação de `task_cycle`, `phases` e `summary`; refazer os `timeout` de `workspace_git` (suba `timeout_multiplier` no `[tool.mutmut]` ou refaça isolados).
- **Limitação conhecida:** a fotografia do git ao redor do agente não sobrevive a uma queda no instante entre o fim da chamada e a transição para `validating`; nesse caso a tentativa segue para os gates sem a checagem.
- **Tabela de idempotência com 12 operações (feito):** sem a operação de push (ADR 0013), e com `create_run_branch`, `normalize_style` (trailer `Stage-Id: normalize-<execução>`) e `rollback_integration` entraram na tabela do código e da spec, com reconciliador e testes. A branch da execução é `forja-run/<execução>` (`run_branch_name`).

## Retomada

- `resume(log, reconcile)` fecha toda operação aberta com um `effect` cujo payload tem `reconciled` (`already_done`, `redo` ou `discard_attempt`) e `infra_failure`. `redo` fecha a operação antiga: quem repete usa um novo `operation_id`. `discard_attempt` leva a tentativa a `discarded` antes do efeito, e repetir a retomada é seguro.
- O intent guarda os insumos da reconciliação no payload; `OpenOperation.payload` os devolve e `RunState.effect_of(id)` devolve o payload do efeito.
- `tests/e2e/driver.py` é um roteiro de teste (não o orquestrador) que percorre as 10 operações da tabela com git, runner, manifesto e artefato reais. `test_resume.py` interrompe após cada linha do log (61 cortes) e rasga a linha em 32 fronteiras de operação; `test_resume_hard.py` mata o processo de verdade em 4 pontos e interrompe a própria retomada. Resultado esperado: igual à execução sem interrupção, exceto `call_agent_cli` interrompido, que dá uma tentativa descartada a mais e uma falha de infraestrutura.
- Marcados `slow`; a suíte inteira leva cerca de 6 min. `TOTAL_LINES` e `TORN_CUTS` são conferidos contra uma execução de referência: se o roteiro crescer, o teste falha.
- Nome de branch: `forja/<run>/<task>` impede que a branch da execução seja `forja/<run>` (conflito de ref). O roteiro usa `forja-run/<run>`; a spec precisa fixar o nome.
- No roteiro, a evidência é um arquivo por chave de cache, não o `EvidenceStore`, e o gate é uma regra fixa. A integração com `GuardedGit` e `GatePipeline` fica para o incremento 1.

## Mutação

- O `mutmut` 3 não roda no Windows; roda no WSL (`Ubuntu-22.04`, com uv). O grupo de dependências é `mutation` (`uv sync --python 3.12 --group mutation` dentro do WSL). A configuração está em `[tool.mutmut]` no `pyproject.toml`.
- Fluxo: copiar o projeto para `~/forja` no WSL (`rsync`, sem `.venv`, `.git` nem `mutants`), apagar `mutants/` e rodar `uv run mutmut run "forja.core.states*"`. Resultados: `uv run mutmut results --all true | grep forja.core.states`; um mutante: `uv run mutmut show <nome>`.
- Escopo combinado: `states/`, `gates/`, `policy/`, `authorization/`, `evidence/`, `events/models.py`, `events/state.py`, `manifest.py`, `redaction/` (regras e PII). Fora: `process/`, `locking/`, `resume.py`, `idempotency/`, `gitguard/`. Meta: todos os mutantes mortos; mutante equivalente é registrado com o motivo.
- Resultado: `states/` 70 de 70 mortos; `gates/` 156 de 156 (um mutante fora da conta: a mensagem do `AssertionError` de ramo inalcançável em `gates/effects.py`, marcada `no mutate`). `redaction/rules.py` e `redaction/pii.py` 210 de 210 (as constantes de módulo, como os padrões de regex, não sofrem mutação: o que as testa é o corpus e a impressão digital das regras; `engine.py`, `record.py` e `settings.py` ficaram fora do escopo combinado); `manifest.py` 135 de 135 (os testes de symlink e de bit de execução só rodam no Linux; fora da conta, `no mutate`: `ensure_ascii` e os separadores do JSON do digest, pois as linhas são listas e só o separador de itens é usado); `events/models.py` e `events/state.py` 199 de 199 (fora da conta, `no mutate`: `ensure_ascii=True` e o codec `"ascii"` em `canonical_json`, que repetem o padrão); `evidence/` 131 de 131 (fora da conta, `no mutate`: a leitura em blocos de `_file_sha256`, que só limita memória e dá o mesmo hash); `authorization/` 74 de 74 (depois de remover o push e as concessões); `policy/` 1.009 de 1.009; fora da conta, marcados `no mutate`: a codificação UTF-8 da leitura de arquivo (igual ao padrão do Linux), o valor `None` de `setdefault` e a opção de caixa em `_check_pattern`, que não muda se o padrão compila. Mutante que vira laço infinito aparece como `timeout` e conta como detectado (`operation_id` no `Journal`). Mutante que aparece como `timeout` numa rodada longa é refeito isolado (`mutmut run <nome>`); os que vimos morreram. Os objetos criados na importação (`EXECUTION_MACHINE` etc.) não sofrem mutação do construtor, porque o mutante só vale dentro de um teste; o teste que cobre o construtor precisa construir o objeto no corpo do teste.
- Primeira execução da suíte no Linux (WSL): 1.666 passaram e 3 falharam, todas fora do escopo da mutação e ainda sem causa investigada: `tests/core/gitguard/test_snapshot.py::test_a_fetch_that_moves_remote_tracking_refs_is_a_change`, `tests/core/locking/test_index_locks.py::test_the_real_process_list_includes_this_process_and_no_invented_names` e `tests/core/locking/test_repository.py::test_the_repository_id_is_short_stable_and_shared_by_every_worktree`. Mais `redaction/test_secrets.py::test_forjas_own_source_is_clean`, que lê o código-fonte e não serve sob mutação. Os quatro estão em `--deselect` na configuração do `mutmut`.

## Estados persistidos (português da spec → inglês do código)

- **Execução:** preparando `preparing`, confirmada `confirmed`, medindo_base `measuring_baseline`, planejando `planning`, executando `executing`, fechando `closing`, pausada `paused`, falhou `failed`, entregue `delivered`, descartada `discarded`.
- **Tarefa:** pendente `pending`, aguardando_dependencia `awaiting_dependency`, em_andamento `in_progress`, integrada `integrated`, bloqueada `blocked`, cancelada `cancelled`.
- **Etapa:** pendente `pending`, em_andamento `in_progress`, pausada_infra `infra_paused`, commitada `committed`, esgotada `exhausted`.
- **Tentativa:** criada `created`, copia_pronta `workcopy_ready`, agente_executando `agent_running`, validando `validating`, aprovada `approved`, rejeitada `rejected`, descartada `discarded`, commitada `committed`.

## Decisões que mudam ou completam a spec

- **Sem criação de PR.** A Forja não integra com plataforma de PR. A entrega é a branch da execução, sempre local: a Forja e o agente nunca fazem push (ADR 0013), e o fim mostra só o comando que o usuário pode rodar. O resumo da execução fica em arquivo no diretório da execução, fora do histórico. A linha "Criação do PR" saiu da tabela de idempotência.
- **Uma sessão da Forja por repositório.** O lock da execução é diretório com dono vivo ou morto (PID e horário de criação do processo). Segunda sessão: `LockPolicy.refuse()` ou `LockPolicy.wait_for(limite)`. O padrão fica a cargo da preparação (incremento 1); a recomendação é `refuse` no modo interativo e `wait` em CI.
- **Estado anterior de `paused` e `failed`** vem do chamador e é rastreado como pilha na reconstrução pelos eventos. `failed` volta ao último estado, inclusive `paused`.
- **`block_task`** (gate inconclusivo com política `block`) é só um efeito. O mapeamento nos estados (tentativa descartada sem contar, etapa esgotada, tarefa bloqueada) é do orquestrador, no incremento 1.
- **A unidade de modo e política é o *check***, não o gate, porque um mesmo gate tem detectores com modos diferentes. Os gates só julgam evidências; as ferramentas rodam em passos de medição, via adaptadores.
- **Adaptadores só descrevem** o comando e interpretam a saída. Quem executa é o núcleo (Job Object, isolamento, mutex, registro). O `config_hash` da chave de cache é calculado pelo núcleo (argv, nomes de variáveis, arquivos de configuração declarados). Os limiares por linguagem vêm da política, não do adaptador.
- **Chave de cache** exclui a versão das políticas e o tipo de medição. Vale só dentro da execução.
- **Eventos** não guardam conteúdo (payload até 4 KiB; linhas de saída cortadas em 1 KiB). `fsync` em tudo menos `progress`. O `started` do executor é persistido como `progress` com `kind="process_started"` e é usado para achar processos remanescentes.
- **Mutex de git** só nos comandos que escrevem, e nunca preso durante a chamada ao agente. Quando houver paralelismo (incremento 7), a fotografia do git deverá ignorar os refs das outras tarefas.
- **Redação** cobre só o que a Forja envia. Não mascara o conteúdo dos arquivos da cópia de trabalho, porque o agente gravaria `[REDACTED]` no código real.
- **Dados em `FORJA_HOME`:** `%LOCALAPPDATA%\forja` no Windows, `~/.local/share/forja` no resto. Execuções em `runs/<id>`, locks em `locks/<id>`.

## Armadilhas já encontradas

- Sequências de escape (`\n`, `\b`, `\x00`) se corrompem ao passar por heredoc de shell. Para código com barras invertidas, usar a ferramenta de escrita, ou `chr()`.
- No Windows, o `python.exe` do venv é um lançador: o PID que um filho grava com `os.getpid()` não é o do `Popen`.
- `Process.wait()` do asyncio só retorna quando os pipes fecham. O executor sonda `returncode`.
- `ruff --fix` apaga importações que ainda não foram usadas. Rodar depois de escrever o uso.
- Os `Protocol` dos adaptadores declaram propriedades somente leitura, para aceitar dataclasses imutáveis.
- Scripts soltos que importam `tests.` precisam de `PYTHONPATH=.`.
- Segredos de teste são montados em tempo de execução a partir de pedaços (`tests/core/redaction/corpus.py`); nunca escrever um segredo completo como literal, porque a Forja passa pelo próprio gate de segredos.

## Limitações conhecidas

- Só foi rodado no Windows. Os ramos POSIX (`_posix.py`, grupos de processo, `/proc`) existem mas não foram exercitados. O teste de Ctrl+Break, o de bit de execução e o de symlink são pulados nesta máquina.
- Nada de WSL ainda. No nível reduzido, a leitura fora da cópia, o acesso à rede e o uso de git em outro caminho são apenas declarados como `detected_only`; nenhum detector existe.
- A redação não detecta nomes, endereços nem segredos codificados, e trata valores só com letras ou só com dígitos depois de um nome de credencial como identificador ou número.
- Os padrões de redação do repositório não são verificados contra ReDoS.
- Um disco mapeado com `subst` não é resolvido no id do repositório.
- O lock fica em `LOCALAPPDATA`, então não protege contra outra máquina no mesmo repositório compartilhado.

- Uma varredura com o próprio redator sobre os 169 arquivos do primeiro commit só achou valores de teste deliberadamente falsos, em `tests/core/isolation`, `tests/core/process` e `tests/core/redaction`. Quando o gate de segredos real (gitleaks, incremento 1) existir, ele vai sinalizar esses mesmos arquivos e precisará de uma lista de exceções para eles.

## Divergências da spec

Atualizadas em `Especificação.md` e `Plano de execução.md`: sem PR (a entrega é a branch `forja-run/<execução>` mais `runs/<id>/resumo.md`), limiares na política, modo por check, Job Object por chamada, fachada restrita de git com fotografia e `GIT_DIR` inexistente, sessão única por repositório, decisões de eventos, redação, chave de cache e diretório de dados. "Não verificável" já era propriedade da operação na spec; não mudou.

## Próximos passos

1. Fechar o incremento 0 (itens da seção "Onde estamos").
2. Incremento 1: esqueleto ponta a ponta. Abre com as perguntas do orquestrador, que ainda não existe: usa os contratos 1 a 5, o lock, a fachada de git e os adaptadores. Decisões pendentes que ele vai precisar fechar: o padrão `refuse`/`wait` do lock, o mapeamento do efeito `block_task` nos estados, valores padrão de tentativas, limites e orçamento (questão aberta 6 do plano), e os nomes de arquivo de configuração (`forja.toml`, `execucao.toml`).
