# Forja — estado do incremento 0

Nota de retomada. Escrita em 10/10/2026, depois de concluídos os contratos 1 a 5, os adaptadores, o lock e a redação do pacote. A especificação (`Especificação.md`) e o plano (`Plano de execução.md`) continuam sendo a referência; este arquivo registra o que foi decidido durante a construção e que não está no código nem na spec.

## Onde estamos

O incremento 0 (fundação) está quase completo. Há 1.771 testes passando e 5 pulados, com `ruff` e `mypy --strict` limpos. Tudo foi executado apenas no Windows.

**Falta para fechar o incremento 0:**

1. ~~Teste de retomada ponta a ponta~~ — feito, em `tests/e2e/` (ver "Retomada").
2. Rodar `mutmut` para medir se os testes pegam mutações de verdade. Nunca foi executado.
3. README e ADRs, em português do Brasil.
4. Atualizar a especificação (lista na seção "Divergências da spec").

## Como trabalhar

```bash
uv sync                 # Python 3.12 via uv; o python do sistema é 3.11
uv run pytest -q
uv run ruff format . && uv run ruff check .
uv run mypy             # strict
```

Dependência de execução: apenas `pydantic>=2.7`. De desenvolvimento: `pytest`, `ruff`, `mypy`. Não adicionar outras sem decisão (a spec restringe).

Convenções: código, comentários e docstrings em inglês; README e ADRs em português do Brasil. Os valores de estado persistidos no JSONL são em inglês (tabela abaixo).

## Mapa dos módulos (`src/forja/core/`)

| Módulo | O que faz |
| --- | --- |
| `states/` | Contrato 1. Máquinas de estado puras dos quatro níveis (execução, tarefa, etapa, tentativa). Só o grafo; guardas ficam no orquestrador. |
| `process/` | Contrato 2. `ProcessRunner` (asyncio): Job Object por chamada no Windows, grupo de processos no POSIX, log bruto, timeout, cancelamento, `stdin_file`, validação de comando (`check_command_safety`). |
| `idempotency/` | Contrato 2. Tabela das 10 operações externas, reconciliadores (só olham) e o auxiliar `Git`. |
| `manifest.py` | Manifesto de uma cópia de trabalho (caminho, SHA-256, tipo, bit de execução), diferença e violações (symlink, maiúsculas, caminho longo). |
| `events/` | Contrato 4. Log JSONL com hash encadeado, estado reconstruído só pelos eventos, recuperação de cauda truncada, versões de esquema. |
| `artifacts/` | Contrato 4. Cabeçalho, armazenamento por hash, os 7 tipos de corpo, contrato de saída do LLM (afirmação, ação, premissa). |
| `evidence/` | Contrato 4. `ToolRun`, `Evidence`, chave de cache e `EvidenceCache`. |
| `records.py` | Armazenamento genérico de registros imutáveis (`ToolRun`, `Evidence`, decisões de gate, pacotes enviados). |
| `gates/` | Contrato 5. Quatro resultados, matriz modo × resultado, `GatePipeline`, registro de decisão. Ainda não há gates reais. |
| `policy/` | Contrato 5. Camadas TOML (código < usuário < repositório < execução), validação, promoção, congelamento em `policy.json`, versão. |
| `authorization/`, `isolation/`, `gitguard/`, `confirmation.py` | Contrato 3. Classes de ação, níveis de isolamento, arquivos sensíveis, ambiente filtrado, `GuardedGit`, fotografia do git. |
| `locking/` | Lock por repositório, mutex de git, remoção de `index.lock` órfão. |
| `adapters/` | Interfaces de adaptador de linguagem e de executor, registro, `TemplateExecutorAdapter`. |
| `redaction/` | Redação do pacote antes do envio, registro do que foi enviado. |
| `resume.py` | Retomada: mata processo remanescente, reconcilia cada operação aberta e grava o efeito. |
| `atomic.py`, `ids.py`, `paths.py`, `failures.py`, `version.py` | Utilitários. |

Os testes ficam em `tests/core/`, espelhando os módulos. `tests/core/adapters/conformance.py` é a suíte reutilizável que todo adaptador real deve passar.

## Retomada

- `resume(log, reconcile)` fecha toda operação aberta com um `effect` cujo payload tem `reconciled` (`already_done`, `redo` ou `discard_attempt`) e `infra_failure`. `redo` fecha a operação antiga: quem repete usa um novo `operation_id`. `discard_attempt` leva a tentativa a `discarded` antes do efeito, e repetir a retomada é seguro.
- O intent guarda os insumos da reconciliação no payload; `OpenOperation.payload` os devolve e `RunState.effect_of(id)` devolve o payload do efeito.
- `tests/e2e/driver.py` é um roteiro de teste (não o orquestrador) que percorre as 10 operações da tabela com git, runner, manifesto e artefato reais. `test_resume.py` interrompe após cada linha do log (61 cortes) e rasga a linha em 32 fronteiras de operação; `test_resume_hard.py` mata o processo de verdade em 4 pontos e interrompe a própria retomada. Resultado esperado: igual à execução sem interrupção, exceto `call_agent_cli` interrompido, que dá uma tentativa descartada a mais e uma falha de infraestrutura.
- Marcados `slow`; a suíte inteira leva cerca de 6 min. `TOTAL_LINES` e `TORN_CUTS` são conferidos contra uma execução de referência: se o roteiro crescer, o teste falha.
- Nome de branch: `forja/<run>/<task>` impede que a branch da execução seja `forja/<run>` (conflito de ref). O roteiro usa `forja-run/<run>`; a spec precisa fixar o nome.
- No roteiro, a evidência é um arquivo por chave de cache, não o `EvidenceStore`, e o gate é uma regra fixa. A integração com `GuardedGit` e `GatePipeline` fica para o incremento 1.

## Estados persistidos (português da spec → inglês do código)

- **Execução:** preparando `preparing`, confirmada `confirmed`, medindo_base `measuring_baseline`, planejando `planning`, executando `executing`, fechando `closing`, pausada `paused`, falhou `failed`, entregue `delivered`, descartada `discarded`.
- **Tarefa:** pendente `pending`, aguardando_dependencia `awaiting_dependency`, em_andamento `in_progress`, integrada `integrated`, bloqueada `blocked`, cancelada `cancelled`.
- **Etapa:** pendente `pending`, em_andamento `in_progress`, pausada_infra `infra_paused`, commitada `committed`, esgotada `exhausted`.
- **Tentativa:** criada `created`, copia_pronta `workcopy_ready`, agente_executando `agent_running`, validando `validating`, aprovada `approved`, rejeitada `rejected`, descartada `discarded`, commitada `committed`.

## Decisões que mudam ou completam a spec

- **Sem criação de PR.** A Forja não integra com plataforma de PR. A entrega é a branch da execução, com push se o usuário o concedeu na preparação. O resumo da execução fica em arquivo no diretório da execução, fora do histórico. A linha "Criação do PR" saiu da tabela de idempotência.
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

## Divergências da spec (a atualizar)

1. Toda menção à criação de PR e à plataforma de PR (tabela de idempotência, estrutura do PR, glossário, questão aberta 5 do plano). O "PR" passa a ser a branch mais o arquivo de resumo.
2. O resumo da execução fica em arquivo, não no corpo de um PR.
3. Limiares por linguagem saem do contrato do adaptador e ficam na política.
4. Modo e política por check, não por gate.
5. Job Object por chamada, em vez de um por execução.
6. Fachada de git restrita (`GuardedGit`), fotografia do git incluindo `.git/config` e hooks, e `GIT_DIR` inexistente no ambiente do agente.
7. `NOT_VERIFIABLE` não existe como veredito de reconciliação; "não verificável" é propriedade da operação.

## Próximos passos

1. Fechar o incremento 0 (itens da seção "Onde estamos").
2. Incremento 1: esqueleto ponta a ponta. Abre com as perguntas do orquestrador, que ainda não existe: usa os contratos 1 a 5, o lock, a fachada de git e os adaptadores. Decisões pendentes que ele vai precisar fechar: o padrão `refuse`/`wait` do lock, o mapeamento do efeito `block_task` nos estados, valores padrão de tentativas, limites e orçamento (questão aberta 6 do plano), e os nomes de arquivo de configuração (`forja.toml`, `execucao.toml`).
