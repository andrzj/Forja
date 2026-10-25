# Forja — plano de execução

## Como este documento governa o trabalho

Este é o documento que mantém a construção da Forja nos trilhos. As regras abaixo valem para qualquer pessoa ou LLM que trabalhe no projeto e mandam sobre notas de sessão e preferências de momento.

1. **Reler antes de toda demanda.** Antes de começar qualquer trabalho, o LLM lê este documento inteiro, em especial a **Fila obrigatória** e o **Registro de andamento**. Nenhuma demanda começa sem essa leitura, mesmo as que pareçam pequenas.
2. **O LLM não escolhe o que fazer.** O trabalho é o do primeiro item da Fila obrigatória que não está concluído, feito por inteiro e na ordem dos passos do plano daquele item. Pular item, antecipar item posterior, acrescentar escopo ou trocar a ordem só com ordem expressa do dono, e a ordem é registrada aqui antes de seguir. Gate ou componente que ninguém alimenta ainda não se constrói à frente do que o alimenta.
3. **Demanda fora da fila.** Se o dono pede algo que não é o próximo item, o LLM diz qual é o próximo item da fila, executa o que foi pedido apenas se for ordem expressa e registra no Registro de andamento que a fila foi alterada e por quê.
4. **Toda atualização do projeto é registrada aqui, no mesmo commit que a causou:** passo concluído, plano escrito, decisão do dono, mudança de ordem, pendência nova. O registro diz data, o que mudou e os commits. O estado da fila (concluído, em andamento, a fazer) é atualizado junto.
5. **Plano antes de código** quando o item toca vários módulos: o plano vai em `docs\plano-<item>.md`, referenciado na fila, e só então se constrói, um passo por commit.
6. **O que fica de fora de todos os itens:** testes E2E reais (são do dono) e qualquer coisa que a Especificação põe em "Fora de escopo".
7. **Divergência.** Se a Especificação e este documento divergem, vale a Especificação; o LLM aponta a divergência e corrige este documento.

## Fila obrigatória

Ordem fixa. O próximo trabalho é sempre o primeiro item não concluído. Cada item cita o plano que o detalha.

| # | Item | Plano | Estado |
| --- | --- | --- | --- |
| 1 | Gate 6, fecho: documentação do usuário e ADR (passo 6) e gate de mutação nos arquivos novos. O E2E real é do dono. | `docs\plano-gate-6.md` | **concluído** (23/10); falta só o E2E real, que é do dono |
| 2 | Incremento 4: documentador (registro de mudança, README, ADR por regra, deriva, voz, citações do documentador, resumo) | `docs\plano-documentador.md` | **concluído** (24/10): passos 0 a 10 |
| 3 | Incremento 6: especificador (critérios, rastreabilidade, `manifesto-testes.json`), arqueólogo, andaime, modo de diretório vazio, premissas e fatos completos, coleta da revisão, gate 13 completo | `docs\plano-especificador-arqueologo.md` | plano escrito; a fazer |
| 4 | Incremento 5, restante: gate 9 (arquitetura) | `docs\plano-gate-9.md` | plano escrito; a fazer |
| 5 | Incremento 5, restante: gate 11 (teste diferencial); depende do item 3 | `docs\plano-gate-11.md` | plano escrito; a fazer |
| 6 | Incremento 3, restante: 3e (cache de medições pela chave completa), os 4 sobreviventes de `mutation\executor.py`, calibração dos limiares com dados de revisão | plano a escrever | a fazer |
| 7 | Incremento 7: endurecimento (paralelismo, mutação incremental, modo CI, adaptador genérico, promoção de gates, documentação de uso, inclusive a sugestão de CLIs diferentes entre papéis) | plano a escrever | a fazer |
| 8 | Fecho: 3f (aceitação e repetição do experimento com duas CLIs reais), execução viva com o Claude Code, E2E real, fixtures e testes `live` | | do dono, por último |

## Registro de andamento

Mais recente primeiro. Cada linha: data, o que mudou, commits.

- **25/10/2026 (fila 3, plano escrito):** `docs\plano-especificador-arqueologo.md` (passos 0 a 8: especificador, manifesto de testes, premissas e fatos, coleta da revisão, arqueólogo e `investigar`, andaime e `criar`, gate 13 completo, fecho). Decisões marcadas como reversíveis no plano: segmentação da entrada em elementos, formato do arquivo de fatos, nome `forja revisao`, `documentar` sai da ajuda, CLI dos papéis novos = a do implementador. Próximo: fila 3, passo 0.
- **24/10/2026 (fila alterada por ordem expressa do dono, fora da fila):** o gate de mutação da própria Forja chamava o binário original do `unclebob/mutator` no WSL, e não o mutator da Forja (`src/forja/mutation`, ADR 0021). Errado: mutação é sempre pelo mutator da Forja, e a Forja roda em qualquer terminal, sem WSL. `scripts/mutate.py` reescrito sobre `forja.mutation` (`discover`, `apply_site`, `run_mutants`): cobertura por teste e supressões como antes, canário no mesmo executor, `PytestRunner` com `PYTHONPATH` da cópia e encerramento da árvore de processos no estouro de tempo; sem `--engine` e sem `--fresh` (o mutator da Forja não tem rodada diferencial). Os testes de link simbólico do passo 10 passaram a simular o link, para valerem no Windows. O resultado do passo 10 (entrada abaixo) foi refeito nesse gate. `docs/estado.md` e os planos dos gates 9 e 11 deixam de citar o WSL. Próximo: fila 3.
- **24/10/2026 (fila 2, passo 10 concluído; fila 2 concluída):** os 52 sobreviventes do gate de mutação nos 13 arquivos do documentador: 46 mortos com testes novos (`test_change_record.py`, `test_symbols.py`, `test_voice.py`, `test_voice_message.py`, `test_comments.py`, `test_readme.py`, `test_readme_paths.py`, `test_readme_gate.py`, `test_doc_drift.py`, `test_doc_drift_gate.py`, `test_adr_trigger.py`) e 6 equivalentes suprimidos em `mutation-suppressions.toml` com aprovação do dono (`fence.group(1)[0]` vs `[1]` em `readme.py` x3 e `doc_drift.py`; `rsplit("/", 1)[-1]` em `adr_trigger.py`; `and -> or` em `comments.py::_judge`). Próximo: fila 3 (plano `docs\plano-especificador-arqueologo.md` a escrever).
- **24/10/2026 (fila 2, passo 10, em andamento):** `docs\documentacao-gerada.md` (onde ficam os registros, como ajustar `[voice]`, o que cada check lê, limites) e ADR 0026 (decisões 2 e 5: a Forja escreve o registro em `docs/mudancas/<tarefa>.md`; README em commit `docs(readme):` próprio; sem validador de tipo de commit). **Divergência com o plano corrigida:** `[documentation] changes_dir` e `[documentation] language` (decisões 2 e 11) não foram construídos, ninguém os pediu; o caminho é fixo e não há verificação de idioma. Gate de mutação no WSL (13 arquivos do documentador): 52 sobreviventes em 11 arquivos, `summary.py`, `citations.py` e `change_record_gate.py` limpos; faltam matá-los.
- **24/10/2026 (fila 2, passo 9):** resumo: a seção “Documentação” do resumo de entrega lista, por tarefa integrada, o registro de mudança, o README e os registros de decisão (ADR) que o documentador deixou, e diz o que não foi conferido (links externos do README; texto do agente fora das afirmações com citação). O ciclo grava o fato no log quando a tentativa do documentador é aprovada (`Measurer.documents`, `summary.DOCUMENTATION`, `Facts.documented`); o resumo continua escrito só a partir do log. As premissas do documentador já entravam em “Premissas assumidas” (mesmo `journal.note`). A preparação e o resumo dizem que o documentador usa a CLI do implementador, sem comandos e só em documentação (não há CLI própria do documentador, decisão 12 do plano). Testes: `test_documentation_summary.py`; `test_details.py` e `test_main.py` ajustados.
- **24/10/2026 (fila 2, passo 8):** ADR por regra: `checksdr_trigger.py` (gatilhos: dependência externa nova, pelo leitor de manifesto, e módulo novo, diretório com arquivo de produção que a tarefa trouxe e que não tinha nenhum na base; `AdrCheck`: gatilho disparado exige um registro novo e numerado em `docs/adr` com seções de alternativas e consequências, número ainda livre; registro a mais não reprova), `CheckSpec("adr", 14, OBSERVATION, PREMISE)`, `Measurer.adr_report` e `AttemptContext.adr` (o que é devido entra no pacote do documentador, redigido), `added_dependencies` extraída de `new_dependency.py`. **Correção de defeito antigo:** `manifests_of` recebia o iterador de `languages()` e o esgotava na primeira pergunta; no `judge` do medidor o gate 10 (`NewDependencyCheck`) não via, portanto, dependência nova alguma; agora `manifests_of` materializa os adaptadores. Testes: `test_adr_trigger.py`, `test_adr_measurer.py`, e um novo em `test_new_dependency.py`.
- **24/10/2026 (fila 2, passo 7):** deriva: `checks\doc_drift.py` (o que está entre crases, fora de bloco de código: caminho, `make alvo` ou `npm run script`, símbolo; símbolo conferido como palavra em qualquer arquivo que não seja documentação, como a prova de não uso do registro) e `checks\doc_drift_gate.py` (`DocDriftCheck`, `read_repository`, `Base` com a catraca: só reprova citação nova, isto é, que o documento não tinha na base da tarefa ou cujo alvo a tarefa removeu), `CheckSpec("doc_drift", 14, OBSERVATION, PREMISE)`, ligado ao `judge` do documentador; registros de `docs/mudancas/` não são lidos. Testes: `test_doc_drift.py`, `test_doc_drift_gate.py`.
- **23/10/2026 (fila 2, passo 6b):** README ligado ao ciclo: `Measurer.readme_report` e `AttemptContext.readme` (o que está errado entra no pacote do documentador), `checks
eadme_gate.py::ReadmeCheck` (seção sem problema que mudou; problema que sobrou) com `CheckSpec("readme", 14, OBSERVATION, PREMISE)`, e `commit_stage(apart=, apart_message=)` nas duas áreas de trabalho: o README vai num commit `docs(readme):` sem `Stage-Id` antes do commit final da etapa. Passo 6 do documentador concluído. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem `test_real_*`) verdes. Testes: `test_readme_gate.py`, `test_documenter_readme.py`, `test_workspace_apart.py` (contrato nas duas áreas de trabalho).
- **23/10/2026 (fila 2, passo 6b, correção e revisão de segurança):** o commit do 6b (`ffa2691`) saiu com 2 testes do medidor falhando (o README novo já estava no índice e `ls-files` o via; trocado por `ls-tree` do `HEAD`), por eu ter comitado sem conferir o resultado da suíte: daqui em diante o commit só vem depois de ler o resultado. A revisão de segurança achou que o alvo de um link do README (texto não confiável) revelava a existência de arquivos fora da árvore e que um README em link simbólico seria lido de fora: `inside`/`exists_inside` recusam caminho absoluto, `..`, unidade de disco e qualquer passo por link, `readme_path` recusa README que seja link, e o relatório do README passa pelo redator antes do pacote. Testes: `test_readme_paths.py` (os 2 de link simbólico são pulados onde o sistema não deixa criar link). Suíte verde: 3331 passaram.
- **23/10/2026 (fila 2, passo 6a):** README, avaliação pura: `checks
eadme.py` (`evaluate`, `chunks`, `signature`, `cited_commands`, `touched_chunks`); comandos comparados por programa e subcomando; símbolos e caminhos citados ficam com a deriva (passo 7). Testes `test_readme.py` (24). Ainda não ligado ao ciclo (6b).
- **23/10/2026 (fila 2, passo 5c):** voz configurável e mensagem de commit: seção `[voice]` (`markers_extra`, `markers_off`) em `core\policy\config.py` e `snapshot.py`, `build_markers`, `AttemptContext.message`, `VoiceCheck(message=)`, notas da preparação. Passo 5 do documentador concluído. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem `test_real_*`) verdes. Testes: `test_voice_policy.py`, `test_voice_message.py`, `test_commit_message_voice.py`, `test_voice_notes.py`.
- **23/10/2026 (fila 2, passo 5b):** gate 12, regras de Ousterhout: `checks\comments.py::CommentsCheck` (comentário novo que repete o código; interface pública nova sem comentário), `CheckSpec("comments", 12, OBSERVATION, PREMISE)`, `Symbol.line` e `Symbol.documented`. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem `test_real_*`): 3265 passaram. Testes: `test_comments.py`.
- **23/10/2026 (fila 2, passo 5a):** gate 12, marcadores de texto gerado: `checksoice_markers.py` (lista versionada com motivo) e `checksoice.py::VoiceCheck` (documentos e comentários adicionados; travessões por arquivo), `CheckSpec("voice", 12, OBSERVATION, PREMISE)` com limite `max_dashes`, ligado ao `judge` de todos os papéis. O passo 5 do plano foi dividido em 5a, 5b (check `comments`) e 5c (lista ajustável em `[voice]` e mensagem de commit). Testes: `test_voice.py`; listas de checks dos outros testes ganharam `voice`.
- **23/10/2026 (fila 2, passo 4):** gate 13 do documentador: `checks\citations.py::CitationCheck` (arquivo e linhas, evidência, fato), `CheckSpec("citations", 13, OBSERVATION, BLOCK)`, `Expectations.claims`, ligado ao `judge` só para o documentador. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem `test_real_*`) verdes. Testes: `test_citations.py`, `test_change_record_measurer.py`.
- **23/10/2026 (fila 2, passo 3):** gate 14 do registro: `checks\change_record_gate.py::ChangeRecordCheck` (seções, arquivos e símbolos recalculados do diff, claim citado), `CheckSpec("change_record", 14, OBSERVATION, BLOCK)`, ligado ao `judge` só para o documentador; `PipelineMeasurer._task_changes` compartilhado com `change_record`. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem `test_real_*`): 3211 passaram. Testes: `test_change_record_gate.py`, `test_change_record_measurer.py`.
- **23/10/2026 (fila 2, passo 2):** documentador no ciclo: etapa final `-d` com commit `docs:`, a Forja escreve `docs/mudancas/<tarefa>.md` (`PipelineMeasurer.change_record`, portas `change_record` e `declared_claims`), `.md`/README/`docs/` classificados como documentação no núcleo, escopo e pacote do papel, planejadores com `DOCUMENTER`, `base-metrics.json`. Suítes `tests/orchestrator tests/core tests/cli tests/checks` (sem slow e sem os `test_real_*`): 3188 passaram. Testes novos: `test_documenter.py`, `test_documenter_role.py`, `test_change_record_measurer.py`.
- **23/10/2026 (fila 2, passo 2, revisão de segurança, duas rodadas):** documentação é `.md`/`.rst` sob `docs/` ou README/CHANGELOG/CONTRIBUTING, exclui famílias de arquivo de instrução de agente e diretórios ocultos; o documentador não escreve registro de outra tarefa, com comparação sem distinção de caixa. Testes em `test_documenter_role.py`.
- **23/10/2026 (fila 2, passo 1):** registro factual do documentador: `checks\symbols.py` (declarações nas seis linguagens, público e forma), `checks\change_record.py` (símbolos criados, alterados e removidos com prova de não uso por referência, renderização determinística, “Porquê” e “Impacto” só de claims citados, `to_body`), `checks.structure.tree_of`, `PipelineMeasurer.metrics` (métricas sem rodar testes). Testes `test_symbols.py`, `test_change_record.py`, `test_measurer.py`. Ainda não ligado ao ciclo (passo 2). Commit abaixo.
- **23/10/2026 (fila 2, passo 0):** leitura e medição do documentador feitas; `docs\plano-documentador.md` corrigido: `.md` é `OTHER` hoje (regra de classificação no núcleo entra no passo 2), o registro de mudança é escrito pela Forja a partir de `claims` validados, sem validador de tipo de commit, `Measurer.metrics` público entra no passo 1, tipos de nó de símbolo medidos nas seis linguagens.
- **23/10/2026 (fila 1 concluída):** gate 6 fechado: `docs\e2e-e-dados-de-teste.md`, ADR 0025, gate de mutação limpo em `personal_data.py`, `e2e.py`, `e2e_plan.py`, `network_trap.py` e `security_notes.py` (testes novos mataram os sobreviventes; `personal_data_in` passou a contar lugares por intervalos disjuntos). Não passaram pelo gate de mutação: as mudanças do `measurer.py` (`BaseE2E`) e de `session.py`/`prepare.py` do passo 5. Próximo: fila 2, `docs\plano-documentador.md`, passo 0.
- **23/10/2026:** o dono apontou desvio da Especificação (infraestrutura de gates construída antes dos papéis que a alimentam). Decididos: este documento passa a governar o trabalho (regras acima); fila fixada; E2E real fora de todos os itens; `docs\plano-documentador.md` escrito. Gate 6, passos 0 a 5 concluídos (`354bf1a`, `f809ab5`, `a2170ad`, `0bd0147`, `76f8c24`, `fd5fe26`, `f325c45`: armadilha de proxy, plano de E2E, `E2ECheck`, `PersonalDataCheck`, integração no medidor e na base).
- **22/10 e 23/10/2026:** gate 10 concluído (passos 0 a 7; ADR 0024). Plano do gate 11 escrito e adiado; planos dos gates 6 e 9 escritos.
- **21/10 e 22/10/2026:** pipeline em todas as linguagens, Gradle, monorepo (passos 1 a 6), CLI por papel (Claude Code, Codex, Cursor, Grok; Gemini suspenso), ADR 0022 e 0023.
- **Antes de 21/10:** incrementos 0, 1, 2 (decisão: seguir, com ressalvas; ADR 0019), 3a e 3b aceitos; mutação completa nas seis linguagens.

## Estado dos incrementos

| Inc. | Estado |
| --- | --- |
| 0, 1, 2 | concluídos |
| 3 | 3a, 3b, 3c e 3d concluídos; 3e e 3f pendentes (fila 6 e 8) |
| 4 | concluído (fila 2) |
| 5 | adaptadores, E2E (gate 6) e segurança (gate 10) feitos ou em andamento; gates 9 e 11 pendentes (fila 4 e 5) |
| 6 | plano escrito; passo 0 a fazer (fila 3) |
| 7 | não iniciado (fila 7) |

## Estratégia

A Forja será construída em incrementos, cada um entregando algo que funciona de ponta a ponta, e a expansão só acontece depois que a tese for medida contra uma linha de base. O risco principal do projeto não é faltar algo no desenho, é tentar construí-lo inteiro de uma vez (efeito segundo sistema, Brooks; lei de Gall: um sistema complexo que funciona evoluiu de um sistema simples que funcionava).

### O que entra na estrutura desde o primeiro dia

Mudar estes pontos depois exigiria refazer o núcleo, por isso eles nascem completos, mesmo que pouco usados no início:

- os cinco contratos centrais: estados e transições, protocolo de subprocesso e idempotência, autorização e isolamento, eventos, artefatos e evidências, e gate;
- esquema único de evidências;
- contratos de artefatos entre papéis;
- interfaces de adaptador de linguagem e de executor;
- contrato de saída do LLM (afirmação, ação, premissa);
- redação do pacote antes do envio.

### Decisões técnicas da implementação

- Python 3.12 ou superior, distribuído como ferramenta instalável por `uv tool` ou `pipx`.
- Esquemas de artefatos e evidências com validação tipada (pydantic).
- Executor de processos assíncrono (asyncio) no núcleo, dono do ciclo de vida dos subprocessos; a interface só consome eventos.
- Interface com Textual sobre Rich; renderizador de texto simples para CI.
- TOML apenas para valores (limiares, modo de cada gate, comandos, limites); predicados e lógica dos gates em código.
- A própria Forja usa o adaptador de Python e passa pelos próprios gates a partir do incremento 1.

## Incrementos

São oito incrementos, de 0 a 7. O incremento 2 é um ponto de decisão: os seguintes só começam se a medição sustentar a tese.

### 0. Fundação

**Escopo:** estrutura do projeto; os cinco contratos centrais como código e testes (máquina de estados, executor de processos com tabela de idempotência, política de autorização, esquemas de eventos, artefatos e evidências com proveniência, contrato de gate com quatro resultados, combinação validada de modo e política, modo observação e chave de cache completa); registros em camadas (execução de ferramenta, evidência, decisão de gate); capacidades declaradas de adaptador; versão de esquema em eventos e artefatos, com conversão na leitura; armazenamento de artefatos por hash; JSONL com hash encadeado, intenção e efetivação; escrita atômica; esquemas de evidências e artefatos; interfaces de adaptador de linguagem e de executor; contrato de saída do LLM; redação do pacote; lock por repositório; testes de injeção de falhas da camada de persistência.

**Pronto quando:** a máquina de estados rejeita transições não permitidas; cada operação da tabela de idempotência tem teste de reconciliação; a retomada chega ao mesmo estado após interrupção em cada fronteira de passo, comprovado por teste; a redação remove segredos e dados pessoais de um conjunto de fixtures conhecidas.

### 1. Esqueleto ponta a ponta

**Escopo:** adaptador de Python; uma CLI; só o papel de implementador; objetivo de refatoração; normalização (`style:`); gates de escopo, segredos, lint com catraca, build, testes e complexidade; gestor de git com branch por tarefa, worktree por tentativa, commit por etapa, integração da tarefa inteira, trailers e verificação de HEAD, índice e refs antes e depois de cada chamada; agente em cópia de trabalho sem .git, com transferência por manifesto para o worktree; build, testes e demais ferramentas executados dentro do sandbox, com caches separados por repositório; isolamento do contrato 3 como ambiente do usuário, declarado (ADR 0018), e Job Object; fachada `forja agente testar`; preparação guiada com descoberta e prova de vida; interface com progresso, atividade do agente e observação do worktree; retomada completa.

**Pronto quando:** em três repositórios Python de exemplo, uma execução vai do comando à entrega sem intervenção; interrupções forçadas em qualquer passo retomam e chegam ao mesmo estado final; uma CLI que tenta usar git falha; a preparação e o resumo declaram o que a Forja impõe e o que fica por conta do ambiente; a própria Forja passa nos seus gates.

### 2. Medição contra linha de base (ponto de decisão)

**Escopo:** experimento com o mesmo conjunto de tarefas executado por uma CLI apenas com prompt e pela Forja. Métricas: taxa de entregas aceitas por um revisor, regressões introduzidas, tempo, tentativas e consumo quando a CLI informar.

**Pronto quando:** relatório com os números e decisão registrada (seguir, ajustar ou parar), com o motivo.

### 3. Prova forte

**Escopo:** papel de autor de testes; gate vermelho/verde; congelamento de testes; mutação e CRAP; métricas opostas (*pass-through*, profundidade de módulo); segunda CLI com diversidade de autor; adaptador de TypeScript; cache de medições pela chave completa do contrato 5.

**Pronto quando:** num conjunto de tarefas com defeitos plantados, testes que não verificam nada são rejeitados pelo gate; uma refatoração que cria métodos rasos é rejeitada mesmo com CRAP melhor.

### 4. Documentação

**Escopo:** papel de documentador como etapa final obrigatória de toda tarefa que altera código; registro de mudança por tarefa; avaliação e correção do README; ADR por regra; deriva; linter de voz para comentários, commits e documentação; resumo da execução e estrutura do resumo de entrega.

**Pronto quando:** toda tarefa aprovada carrega seu registro no mesmo commit; um README com comando de build divergente é detectado e corrigido apenas na seção afetada.

### 5. Amplitude

**Escopo:** adaptadores de Java, Go e C#; JavaScript completo; modelo arquitetural global (grafo, ciclos, métricas de pacote, camadas); teste diferencial com medição de tempo e memória; E2E com fakes e rede desligada; segurança completa (Semgrep, OSV-Scanner, licenças, verificação de dependência nova).

**Pronto quando:** a suíte de avaliação, com repositórios de exemplo nas seis linguagens, executa ponta a ponta; uma refatoração que cria ciclo de dependência é rejeitada; um E2E que acessa rede falha.

### 6. Ideia, especificação e engenharia reversa

**Escopo:** papéis de arqueólogo e especificador; rastreabilidade ideia → critério → teste; andaime determinístico por template; modo a partir de diretório vazio; premissas e fatos registrados completos; coleta do resultado da revisão a partir do git.

**Pronto quando:** a partir de uma especificação de exemplo, a Forja entrega um projeto com testes que cobrem todos os critérios; a documentação de engenharia reversa separa fatos provados, fatos confirmados e premissas.

### 7. Endurecimento

**Escopo:** paralelismo de tarefas com escopos disjuntos; mutação incremental; prevenção de suspensão; modo CI com `--config`; adaptador genérico de CLI; calibração de limiares e promoção de gates do modo observação para bloqueante com dados da revisão; documentação de uso da Forja.

**Pronto quando:** a suíte de avaliação roda em CI a cada mudança de política ou de versão de CLI, e os limiares estão calibrados com dados reais de revisão.

## Riscos e mitigação

| Risco | Impacto | Mitigação |
| --- | --- | --- |
| Escopo excessivo na primeira versão | Projeto longo sem entrega útil | Incrementos com critério de pronto; decisão explícita no incremento 2 |
| A tese não se confirma na medição | Investimento sem retorno | Incremento 2 antes de qualquer expansão; critérios de sucesso definidos antes |
| CLIs mudam flags, formatos de saída e comportamento com frequência | Execuções quebram após atualizações | Adaptadores isolados; prova de vida por versão; suíte de avaliação a cada atualização |
| Gates rígidos demais bloqueiam quase tudo; frouxos demais aprovam código ruim | Ferramenta inútil ou perigosa | Catraca; limiares por linguagem; modo observação para gates sem calibração; calibração com dados da revisão |
| Mutação lenta em repositórios grandes | Execuções de muitas horas | Mutação incremental e restrita ao código tocado; cache pela chave completa |
| Ferramentas de mutação imaturas em Go e Python | Falsos resultados | Limiares próprios; mutação como métrica informativa onde for frágil |
| Fakes divergem dos serviços reais | E2E verdes com comportamento real quebrado | Fakes gerados ou validados por contrato; divergência possível declarada como premissa |
| Restrições corporativas (containers, rede, instalação de ferramentas) | Ferramentas indisponíveis | A Forja não depende de WSL, Linux ou contêiner; o `doctor` aponta o que falta e a confirmação declara o que o ambiente deve garantir (ADR 0018) |
| Terminal do Git Bash (mintty) incompatível com interface rica | Experiência degradada | Detecção e aviso; recomendação de Windows Terminal; renderizador de texto simples |
| Envio de código sensível ao provedor do modelo | Exposição de dados | Redação obrigatória do pacote; exclusões por configuração; auditoria do pacote enviado |
| Agente altera o git (commit, reset, refs compartilhadas pelo worktree) | Estado da execução inconsistente; retomada incorreta | Agente em cópia sem .git; verificação de HEAD, índice e refs antes e depois de cada chamada, desde o incremento 1 |
| Ferramenta de medição falha ou não suporta o código | Aprovação silenciosa ou culpa indevida do agente | Resultado inconclusivo com política por gate (contrato 5) |
| Evidência reaproveitada de outro contexto de medição | Gate decide com dado desatualizado | Chave de cache com commit, ferramenta, configuração, toolchain, plataforma e escopo |
| CLI lê arquivos que não estavam no pacote | Dados sensíveis expostos ao provedor do modelo | Cópia de trabalho sem arquivos sensíveis; ferramentas de arquivo da CLI confinadas à cópia; o resto é declarado como do ambiente |
| Falhas de infraestrutura repetem chamadas à CLI | Custo sem limite | Consumo por chamada; limite de falhas consecutivas por etapa; pausa da execução |
| Evolução do formato de eventos e artefatos | Execuções antigas não retomam ou retomam errado | Versão de esquema; conversão na leitura; recusa explícita de versão desconhecida |
| Alterações do agente não representáveis no worktree (links simbólicos, nomes que diferem só em maiúsculas, caminhos longos) | Worktree inconsistente com a cópia | Transferência por manifesto; tentativa rejeitada com motivo explícito |

## Questões em aberto para a revisão

Pontos que ainda não têm decisão e que a revisão deve ajudar a fechar:

1. **Limiares iniciais por linguagem:** CRAP, complexidade, cobertura e score de mutação para começar, antes de haver dados de calibração.
2. **Formato das políticas:** decidido: predicados em código e TOML apenas para valores. Falta definir o esquema desses valores por linguagem.
3. **Isolamento:** decidido (ADR 0018): a Forja roda no ambiente do usuário e não cria sandbox; a infraestrutura e as permissões em volta são do usuário ou da empresa.
4. **Consumo de tokens:** nem todas as CLIs informam consumo de forma estruturada; definir se o custo será medido por tokens, tempo ou ambos. Fontes possíveis: a própria CLI ou os relatórios do gateway corporativo; a Forja não intermedia as chamadas ao modelo.
5. ~~**Plataforma de PR**~~ — decidido: sem PR e sem integração com plataforma. A entrega é a branch da execução mais o resumo; a coleta da revisão usa só o que o git mostra.
6. **Valores padrão:** número de tentativas por tarefa, limite de arquivos e linhas por tarefa, limite de tarefas por execução e orçamento de tempo.
7. **Tamanho máximo do pacote** de evidências e critério de corte quando os hotspots excederem esse limite.
8. **Conjunto de repositórios da suíte de avaliação:** quais projetos de exemplo, com quais defeitos plantados, em cada linguagem.
9. **Nome e distribuição interna** da ferramenta.
10. **Padrão do lock por repositório:** recusa imediata ou espera com limite quando houver outra sessão da Forja (recomendação: recusa no modo interativo, espera em CI). Fecha-se no incremento 1.
