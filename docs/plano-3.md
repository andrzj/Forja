# Incremento 3 — Prova forte: plano em sub-incrementos

Escrito em 12/10/2026. Estado: fatiamento, ordem e **plano detalhado do 3a aprovados** (perguntas 11 a 15 respondidas "sim"). Passos 1 a 9 do 3a feitos (mutação diferencial adiada para o 3b; aceitação em `docs\aceitacao-3a.md`). Cada sub-incremento terá seu plano detalhado e sua aprovação no começo dele; este documento fixa o fatiamento, a ordem, as entregas e os riscos.

## Referências lidas

- Plano de execução, seção 3 (escopo e "pronto quando").
- Especificação: papéis (tabela de contratos de artefatos), diversidade de autor, gates 5, 7 e 8, medidores próprios, padrões para detectores frágeis, chave de cache.
- `docs\estado.md`: política de mutação (mutator e crapper), ADR 0018 (sem WSL no produto), cache de evidências.
- Código visto: `Producer.TEST_AUTHOR` já existe em `src\forja\core\artifacts\models.py`; `ClaudeCodeAdapter` (`permission_setup`, `plan_invocation`, `parse_event`) em `src\forja\executors\claude_code.py`; `cache_key` e `EvidenceCache` em `src\forja\core\evidence\cache.py`; `ExecutorAgentRunner` em `src\forja\orchestrator\agent_runner.py`.

## Respostas do dono (perguntas 3 a 6)

3. Segunda CLI: o desenho deve ficar preparado para as principais do mercado: Claude Code, Codex, Cursor, Gemini CLI e Grok Build.
4. A Forja constrói o conjunto de tarefas com defeitos plantados, definidos e registrados antes de qualquer execução. Aprovado.
5. O experimento Forja contra linha de base **será repetido** ao final do incremento 3.
6. Resposta "OK". Leitura adotada: a pergunta "A também formata?" fica registrada, sem rodada própria agora. Ver 3f, que a absorve a custo baixo. Se a intenção era rodar já, avisar.

## Visão geral

| Sub | Entrega | Gates da spec | Depende de |
| --- | --- | --- | --- |
| 3a | Autor de testes, gate vermelho/verde, congelamento | 1 (escopo por tipo), 5 (congelados) | nada |
| 3b | Mutação, CRAP e métricas opostas | 7, 8 | 3a |
| 3c | Mais CLIs, diversidade de autor por papel | — | 3a |
| 3d | Adaptador de TypeScript | todos, para TS | 3b |
| 3e | Cache de medições pela chave completa | — | 3b (a mutação é a medição cara) |
| 3f | Aceitação e repetição do experimento | — | 3a a 3e |

3c e 3e não dependem entre si e podem trocar de ordem. 3e pode subir para logo depois de 3b se a mutação pesar nas execuções.

## 3a — Autor de testes, gate vermelho/verde e congelamento

**Objetivo.** Um segundo papel escreve testes antes do implementador; os testes entram congelados; o implementador não pode alterá-los.

**Passos.**
1. Conjunto de tarefas com defeitos plantados (item 4 das respostas). Repositórios pequenos, em Python, com defeito conhecido, descrição em texto, critérios numerados escritos à mão e um teste de referência que só nós temos. Os defeitos e os testes vazios que devem ser rejeitados (sem asserção, asserção sempre verdadeira, teste que não chama o código) são registrados em documento antes de qualquer execução, como foi feito em `docs\medicao-2.md`.
2. Contrato `manifesto-testes.json` (critério → teste) e esquema, sobre o que já existe em `core\artifacts`. Em 3a os critérios vêm de lista fornecida com a tarefa; o especificador só chega no incremento 6.
3. Papel `TEST_AUTHOR` no executor: pacote, permissões de escrita só em arquivos de teste e fixtures (gate 1 por tipo de arquivo, usando a classificação de teste e produção do adaptador de Python).
4. Gate vermelho/verde. Caracterização passa no código atual. Comportamento novo (correção) falha no código atual. Todo critério coberto pelo manifesto. Um teste que passa no código com o defeito é rejeitado: isso já elimina o teste vazio nas tarefas de correção.
5. Congelamento: ao aprovar a etapa de testes, grava-se o hash dos arquivos; a etapa do implementador reprova se qualquer um mudou (gate 5, "testes congelados foram alterados").
6. Ciclo por tarefa no orquestrador: testes (vermelho) → implementação (verde), com commit por etapa.

**Pronto quando.** Em cada tarefa do conjunto, o teste vazio é rejeitado pelo gate vermelho; o teste bom passa; alterar um teste congelado reprova a etapa do implementador; a retomada continua funcionando nas novas fronteiras (teste de corte como o do incremento 1).

**Riscos.** Hoje só existe o objetivo "refatorar". Ver pergunta 7. Teste de caracterização de refatoração só fica seguro com mutação (3b); em 3a o gate vermelho cobre as tarefas de correção.

## 3b — Mutação, CRAP e métricas opostas

**Objetivo.** Gates 7 e 8 no produto, usando `unclebob/mutator` e `unclebob/crapper`, e as duas métricas opostas.

**Passos.**
1. Spike curto, sem código de produção: rodar mutator e crapper **no Windows nativo** contra um alvo Python pequeno e contra o canário de `scripts\mutate.py`. Hoje eles rodam só no WSL (nosso gate de desenvolvimento); o ADR 0018 proíbe WSL no produto. Resultado do spike decide o resto (pergunta 8).
2. Check de cobertura e mutação sobre as linhas alteradas pela tentativa (regra já decidida em `estado.md`: nenhum sobrevivente em linha alterada e coberta; linha alterada sem cobertura é achado à parte). Canário antes do veredito, como em `scripts\mutate.py`.
3. Check de CRAP por função, a partir da complexidade (lizard, já usado no gate 8 atual) e da cobertura.
4. Medidores próprios, em AST: métodos *pass-through* e razão interface/implementação (profundidade de módulo). Antes de virarem gate, validação contra referência num repositório conhecido (regra da spec) e conjunto de exemplos bons e ruins escritos à mão.
5. Modo de cada check na política: começam em `observacao` (spec), e a suíte de aceitação roda com política que os torna bloqueantes.
6. O gate de mutação roda também sobre os testes do autor de testes, o que fecha o caso de testes de caracterização vazios em refatoração.

**Pronto quando.** Refatoração que cria métodos rasos é rejeitada mesmo com CRAP melhor (caso construído de propósito e registrado); testes vazios de caracterização são rejeitados pela mutação; os medidores próprios passam na validação contra a referência.

**Riscos.** Mutator e crapper são de um só autor e podem não rodar no Windows; plano B: manter a porta e um adaptador próprio mínimo. O custo de tempo da mutação é alto (a rodada completa da Forja levou cerca de uma hora); por isso o escopo é só linhas alteradas. A spec marca *pass-through* e profundidade como detectores frágeis, com falso positivo, por isso começam em observação.

## 3c — Mais CLIs e diversidade de autor

**Objetivo.** O autor de testes e o implementador podem rodar em CLIs diferentes, configuradas por papel. O desenho aceita as cinco CLIs; o aceite do incremento exige duas.

**Passos.**
1. Configuração por papel (`cli` por papel no `execucao.toml`, hoje há um `cli` só) e regra da spec: sugerir CLIs diferentes entre testes e implementação quando houver mais de uma disponível. O `forja doctor` e a descoberta passam a listar todas as instaladas.
2. Um adaptador por CLI atrás da mesma porta que o `ClaudeCodeAdapter` usa, cada um como sub-passo próprio e com os mesmos testes de contrato: Codex, Cursor, Gemini CLI, Grok Build. Para cada uma, no começo do passo, ler a documentação oficial: modo headless, formato de eventos, modelo de permissões, como confinar escrita à cópia, onde sai o uso de tokens. **Nada disso será escrito de memória.**
3. Cada adaptador entra com gravações de saída reais (fixtures), prova de vida e prova de contenção opt-in, como em `tests\executors\test_live.py`.
4. Ordem sugerida: a primeira é a que estiver instalada e autenticada nesta máquina e tiver modo headless documentado; as demais conforme o dono tiver acesso.

**Pronto quando.** Uma execução com autor de testes na CLI A e implementador na CLI B entrega; o resumo mostra qual CLI fez cada papel; cada adaptador novo passa nos testes de contrato.

**Riscos.** Não tenho como confirmar agora que o Grok Build tem modo headless e saída estruturada; se não tiver, fica de fora até ter (pergunta 9). Cada CLI muda rápido, daí a prova de vida por versão que já existe. Custo: cada prova viva gasta tokens e exige login do dono.

## 3d — Adaptador de TypeScript

**Objetivo.** Segundo adaptador de linguagem, com todos os gates que existem hoje.

**Passos.**
1. Ao começar: levantar as ferramentas de formatação, lint, build, teste e cobertura mais usadas e como detectá-las pela configuração do repositório (a configuração do repositório prevalece). A escolha concreta fica para o plano detalhado do 3d.
2. Adaptador que só descreve comandos e interpreta saída (ADR 0004); classificação de arquivos de teste e produção; limiares na política (ADR 0005).
3. Complexidade: lizard já cobre TypeScript pelo README; confirmar.
4. Mutação e CRAP em TypeScript pelas mesmas ferramentas (o README do mutator cita TypeScript), com o mesmo spike do 3b.
5. Medidores *pass-through* e profundidade via tree-sitter, se o AST de Python do 3b não servir (a spec cita tree-sitter).
6. Dois ou três repositórios TypeScript de exemplo, com defeitos plantados.

**Pronto quando.** Uma execução completa em repositório TypeScript de exemplo passa por todos os gates; o adaptador tem os mesmos testes de contrato do de Python.

**Riscos.** Ambiente de Node no Windows do usuário; versão do gerenciador de pacotes; tempo de instalação por repositório.

## 3e — Cache de medições pela chave completa

**Objetivo.** Não refazer medição quando a chave inteira do contrato 5 coincide.

**Passos.**
1. Verificar o que `core\evidence\cache.py` já cobre (`cache_key`, `EvidenceCache.put/has/find`) e onde `PipelineMeasurer` mede sem consultá-lo.
2. Ligar o medidor ao cache: consultar antes de rodar, gravar depois, reaproveitar só com a chave inteira (commit, ferramenta e versão, hash da configuração efetiva, toolchain, plataforma, escopo medido).
3. Respeitar o ADR 0010: a chave não leva versão da política nem tipo de medição, e o cache vale dentro da execução.
4. Teste: segunda medição idêntica não cria processo; qualquer componente da chave diferente refaz; evidência reaproveitada fica marcada como tal no log.

**Pronto quando.** Medição repetida com chave igual não executa a ferramenta (provado por contagem de processos); mudança em qualquer componente da chave refaz.

**Risco.** Reaproveitar errado é pior do que refazer; por isso o teste por componente da chave.

## 3f — Aceitação e repetição do experimento

**Objetivo.** Provar o "pronto quando" do incremento e repetir a medição Forja contra linha de base.

**Passos.**
1. Aceitação do incremento: tarefas com defeitos plantados (testes vazios rejeitados) e refatoração rasa rejeitada mesmo com CRAP melhor, registradas em `docs\aceitacao-3.md`.
2. Protocolo do experimento em `docs\medicao-3.md`, **escrito e commitado antes de rodar**, com regra de decisão fixada. Pontos a decidir no plano detalhado: tarefas mais difíceis (a rodada 2 saiu com efeito teto parcial), incluir tarefas de correção com defeitos plantados, e o braço de linha de base **com formatação** (resposta à pergunta aberta do incremento 2, sem rodada separada).
3. Orçamento de tokens antes de rodar; o dono aprova o teto (no incremento 2 foram cerca de 470 mil no total).
4. Relatório e ADR com decisão do dono.

**Pronto quando.** Relatório com números, decisão registrada com o motivo, e `estado.md` e `Plano de execução.md` atualizados.

## Decisões do dono (perguntas 7 a 10, 12/10)

7. Sim: abrir o objetivo "corrigir" no 3a.
8. Sim: se o mutator e o crapper não rodarem no Windows nativo, faz-se um adaptador próprio mínimo de mutação para Python, sem WSL (o dono ainda aprova o desenho antes de escrever).
9. Só o Claude Code por enquanto. Em 3c, a diversidade de autor entre CLIs reais fica **adiada** até haver uma segunda CLI instalada e autenticada; o desenho por papel e a porta de adaptador continuam no escopo, provados com executor falso e com o Claude Code nos dois papéis.
10. Ordem confirmada: 3a, 3b, 3c, 3d, 3e, 3f. Com a 9, o 3c encolhe (configuração por papel, descoberta de várias CLIs, contrato de adaptador testável sem CLI real) e o aceite "duas CLIs" do 3f passa a ser "dois modelos ou duas configurações do Claude Code" até haver outra CLI; **o dono confirma essa troca no plano do 3c**.

---

# Plano detalhado do 3a

## O que o código tem hoje (visto)

- `Producer.TEST_AUTHOR` existe; `ArtifactType.TEST_MANIFEST` e `CRITERIA` existem; `AuthoredTestsBody` (lista de `CriterionTest` com `criterion_id`, `test_id`, `path`; geradores) e `CriteriaBody` (`Criterion`: `id`, `text`, `level`, `origin`) existem em `core\artifacts\schemas.py`.
- `ExecutorAgentRunner` já recebe `role` e `permissions` (`orchestrator\agent_runner.py`), então chamar a CLI com outro papel não exige um runner novo.
- `FileClass` tem `PRODUCTION`, `TEST`, `FIXTURE`, `DOCUMENTATION`, `OTHER`; o adaptador de Python já classifica (`languages\python\adapter.py`).
- `ScopeCheck` (`checks\scope.py`) hoje aceita **só** arquivos de produção ("only production files may change in a refactoring"). Precisa saber quais classes o papel pode alterar.
- `TaskCycle` (`orchestrator\task_cycle.py`) tem **uma etapa por tarefa** (`{task_id}-s`) e chama sempre o mesmo `AgentRunner`. `PipelineMeasurer.judge` monta sempre a mesma lista de checks, sem noção de papel.
- `RunConfig.objective` só tem `REFACTOR`; `RunConfig` tem só `implementer`.
- Não li ainda: `core\states\stage.py` e `task.py` (se uma tarefa admite duas etapas em sequência e como a tarefa vira `integrated`), `planner.py`, `cli\session.py` e `cli\prepare.py` (como o verbo `corrigir` chega à configuração). Ler no começo da implementação.

## Correções do passo 1 (leitura do código, 12/10)

Fatos vistos que corrigem ou precisam de ressalva no plano abaixo:

- `stage.py` e `task.py`: nada impede duas etapas por tarefa; **não há estado novo**. O limite é o `TaskCycle` (`TaskInfo.stage_id` único, `{task_id}-s` fixo em `task_cycle.py:61`).
- `_finish` (`task_cycle.py:342-379`) lê uma etapa só e integra a tarefa quando ela é `committed`. Com duas etapas, só integra depois da etapa 2; etapa 1 `exhausted` bloqueia a tarefa.
- `attempts_per_task` **já conta por etapa** (`quality_attempts(state, info.stage_id)`, `task_cycle.py:98`); a pergunta 15 sai de graça.
- `corrigir` **já existe como verbo** (`cli\args.py:16`), mas `cli\prepare.py:23` (`AVAILABLE`) só libera `refatorar` e `objective_of` recusa `corrigir`. `-f`/texto são só parseados (`args.py:51-52`); **ninguém lê** `Arguments.file` nem `text`. A leitura do defeito e de `criterios.json` é do zero. `objective=Objective.REFACTOR` está fixo em `cli\session.py:152`; `cli\settings.py:39` tem `Literal["refatorar"]`; o texto "Vou refatorar" é fixo (`prepare.py:208`).
- `ComplexityPlanner` é fixo (`session.py:297`) e `PlannedTask` não tem etapas nem raiz de testes; o payload PENDING só leva `intent`, `scope`, `max_files`, `max_lines`. Precisa de planner novo para `FIX` e campos novos no payload.
- `ScopeCheck` é montado dentro de `PipelineMeasurer.judge` (`measurer.py:252`), sem noção de papel ou etapa. Papel/etapa tem de entrar em `AttemptContext` e `judge`.
- `RunContext.agent` é um runner só (`ports.py:181`); vira mapa papel → runner.
- Commit fixo: `CommitMessage.refactor` e `config.implementer` (`task_cycle.py:254-258`); generalizar para o autor de testes.
- Pytest: `TestsCheck` não distingue falha de asserção de erro de coleta (só o rótulo `FAILED` vs `ERROR`, `parsers.py:22,106-125`). Nenhum check usa `OperationRequest.test_files` ainda (só o contrato e o adaptador Python). O check vermelho/verde precisa de leitura própria dos outcomes.
- Não lidos ainda: `schemas.py` (`AuthoredTestsBody`) e `agent_runner.py` (`_declared`); ler no passo 3/7.

Efeito no plano: passos 3 e 4 crescem (CLI e planner partem do zero; `_finish`, `TaskInfo` e commit mudam). Ordem e escopo do 3a ficam como aprovados.

## Desenho

**Entrada do `corrigir`.** `forja corrigir "texto"` ou `-f arquivo` já existe como forma do comando. O texto descreve o defeito. Os critérios vêm de um arquivo `criterios.json` no formato de `CriteriaBody` (campo `origin` = "usuário"), ao lado do `-f` ou por `--criterios`. Esse arquivo é o único caminho de critérios no 3a; o especificador (incremento 6) o substituirá, e o contrato continua o mesmo.

**Duas etapas por tarefa.** Etapa 1, autor de testes; etapa 2, implementador. Cada uma tem suas tentativas, seu commit e seu orçamento de tentativas (`attempts_per_task`). A etapa 2 só começa depois do commit da 1. Uma tarefa de correção é uma só tarefa com as duas etapas. A tarefa de refatoração continua com a etapa do implementador apenas.

**Papel por etapa.** O `RunContext` passa a ter um runner por papel (`agent` vira mapa papel → runner, com o implementador como padrão). `RunConfig` ganha `test_author: ExecutorRef | None`; `None` significa o mesmo executor do implementador. O campo novo é opcional, então a leitura de configurações antigas não quebra.

**Escopo por papel.** `ScopeCheck` ganha o conjunto de classes permitidas: autor de testes → `TEST` e `FIXTURE`; implementador → `PRODUCTION`. Qualquer outra classe reprova, como hoje. A tarefa de correção declara o escopo de produção (para o implementador) e uma raiz de testes (para o autor).

**Gate vermelho/verde (novo check, gate 5 estendido).**
- Roda depois dos checks baratos (escopo, segredos, formatação, lint, build), antes dos testes completos.
- Etapa do autor de testes, **no worktree da tentativa**: (a) os testes novos devem **falhar** no código atual; (b) os testes que já existiam devem continuar passando; (c) todo critério do `criterios.json` aparece em pelo menos um `CriterionTest` do manifesto, e todo caminho do manifesto existe e é um arquivo de teste; (d) um teste que passa no código com o defeito é rejeitado, com mensagem dizendo qual.
- Para chamar só os testes novos, usa `OperationRequest.test_files` (já existe no contrato do adaptador).
- Diferença entre falha "boa" e falha "ruim": um teste que falha por erro de importação, de sintaxe ou de coleta **não conta como vermelho**. O adaptador de Python precisa distinguir falha de asserção de erro de coleta na saída do pytest (hoje o parser lê `pytest -rA`; **conferir se a saída já separa as duas coisas**).
- Etapa do implementador: todos os testes do manifesto devem passar (verde), além dos checks de hoje.

**Congelamento.** Ao commitar a etapa 1, grava-se o hash dos arquivos de teste e fixtures dela (manifesto de conteúdo, `core\manifest.py`). Na etapa 2, um check novo compara; qualquer mudança em arquivo congelado reprova (também cobre apagar e renomear). O conjunto congelado entra no registro de eventos, para a retomada recalcular sem ler o worktree.

**Pacote do autor de testes.** Descrição do defeito, critérios, arquivos de produção em escopo (só leitura, no pacote), regras do papel (não toca produção; cada critério tem teste; declara o manifesto em `saida.json`), e a rejeição anterior. O manifesto vem no mesmo canal de saída estruturada que o implementador já usa (`_declared` em `agent_runner.py`); o formato é o de `AuthoredTestsBody`.

**Retomada.** As novas fronteiras (fim da etapa 1, início da etapa 2, gravação do congelamento) entram nos testes de corte existentes (`tests\orchestrator\test_resume_end_to_end.py`). Operações novas passam pela tabela de idempotência só se escreverem fora do log; o congelamento é um evento, não uma operação com efeito externo (a confirmar ao ler o `Journal`).

## Passos (cada um termina com testes e gates verdes)

1. **Ler o que falta** (lista acima) e escrever aqui a correção deste plano, se o código desmentir algo.
2. **Conjunto de defeitos plantados**, em `scripts\medicao\repos` ou pasta nova ao lado: 4 repositórios Python pequenos; para cada, defeito, descrição, `criterios.json`, teste de referência oculto, e uma lista de **testes ruins** a serem rejeitados (sem asserção, `assert True`, não chama o código, falha por erro de importação, passa com e sem o defeito). Documento `docs\defeitos-3.md` escrito e commitado **antes** de qualquer execução.
3. **Objetivo e configuração:** `Objective.FIX`, `RunConfig.test_author`, entrada `corrigir` com `criterios.json` (`cli\prepare.py`, `cli\session.py`), validação do arquivo e mensagem de erro clara.
4. **Duas etapas na máquina de execução:** `TaskCycle` com lista de etapas por tarefa, runner por papel, commit por etapa com os trailers existentes; planner para o objetivo `FIX` (uma tarefa, duas etapas). Testes de ponta a ponta com agente roteirizado (`tests\orchestrator\fakes.py`).
5. **`ScopeCheck` por papel** e testes: cada classe de arquivo, por papel, aceita e recusada; renomear teste para produção e o inverso.
6. **Check vermelho/verde** e **congelamento**, com o parser de pytest distinguindo falha de asserção de erro de coleta. Testes contra os "testes ruins" do passo 2.
7. **Pacote e saída do autor de testes**, com gravação real do Claude Code (opt-in `live`, como `tests\executors\test_live.py`; exige login do dono e gasta tokens).
8. **Retomada:** cortes nas fronteiras novas — feito em `tests\orchestrator\test_fix_resume.py` (101 casos, mundo em memória, fora do `slow`). Mutação diferencial: ADIADA para o 3b por decisão do dono (mutator e crapper devem ser reimplementados como versão da Forja, sem WSL). Alvos a mutar quando o motor existir: `checks\{scope,red_green,freeze}.py`, `core\artifacts\llm_output.py`, `orchestrator\{task_cycle,measurer,agent_runner,planner}.py`.
9. **Aceitação do 3a** em `docs\aceitacao-3a.md`: cada teste ruim do passo 2 é rejeitado; o teste bom passa; alterar teste congelado reprova; uma execução viva com o Claude Code nos dois papéis em ao menos 2 dos 4 repositórios.

## Pronto quando

Cada "teste ruim" registrado é rejeitado pelo gate com a causa certa; o teste bom é aceito e a etapa do implementador chega ao verde; mexer em arquivo congelado reprova; as retomadas por corte terminam no mesmo estado; a própria Forja passa nos seus gates (`ruff`, `mypy src tests`, testes rápidos, mutação diferencial).

## Perguntas do 3a — respondidas "sim" a todas em 12/10 (plano do 3a aprovado)

As propostas abaixo valem como decisões.

11. **Formato de `criterios.json`.** Proposta: exatamente `CriteriaBody` (lista de `{id, text, level, origin}`), com `origin` livre. Serve, ou prefere outro formato (por exemplo uma lista de frases no próprio arquivo de descrição)?
12. **Quem escreve os critérios nas tarefas do experimento?** Proposta: eu, junto com o conjunto de defeitos do passo 2; você revisa `docs\defeitos-3.md` antes de qualquer execução.
13. **Erro de coleta.** Proposta: erro de importação, sintaxe ou coleta **não** conta como vermelho; a tentativa é rejeitada com a mensagem do pytest. Concorda?
14. **Teste que já existia e passa a falhar.** Proposta: reprova a etapa do autor de testes (o autor não pode quebrar a suíte). Concorda?
15. **Orçamento de tentativas.** Hoje `attempts_per_task` = 3 vale por tarefa. Proposta: passa a valer por etapa (3 para o autor e 3 para o implementador), com o teto de tokens da execução inalterado. Concorda?

# Plano detalhado do passo 6 (vermelho/verde e congelamento)

Decisões do dono (12/10, "sim" a todas as propostas 1 a 6 e à divisão 6a/6b). O código foi mapeado antes (ver "Fatos vistos").

## Fatos vistos

- `TestsCheck` está em `checks\build_and_tests.py:44` (gate 5). O parser de pytest (`languages\python\parsers.py:106-125`) lê `pytest -rA`; o regex da linha 22 descarta o texto depois de " - ". Cada teste vira um `EvidenceDraft` `test.outcome` com valor `passed|failed|error|xfail|xpass`; o id é `path::nome`.
- `OperationRequest.test_files` existe; o adaptador de Python o passa a `pytest -- <arquivos>` (`adapter.py:158-163`).
- Todo check precisa de entrada em `CheckSettings` (`core\gates\pipeline.py:76-78`), senão o pipeline levanta erro. A ordem dentro do mesmo gate é a de registro.
- O `saida.json` só é lido por `agent_runner._declared` (`agent_runner.py:452-464`); `LlmOutput` não tem campo de testes. `judge` (`measurer.py:241`) não recebe critérios nem manifesto.
- No gate da etapa 1, o worktree é a base mais o diff não commitado do autor, sem produção alterada (garantido pelo `ScopeCheck`). Na etapa 2, o HEAD já traz o commit da etapa 1.
- O payload de transição tem teto de 4096 bytes (`core\events\models.py:23`). `journal.enter(level, id, to, payload=...)` e `state.transition_payload(...)` permitem gravar e reler sem o worktree.
- A ramificação de retomada em `task_cycle.py:155` entra em `STAGE COMMITTED` sem payload.

## Decisões

1. Canal do manifesto: campo opcional `tests` em `LlmOutput`, no formato de `AuthoredTestsBody`; `_declared` o lê e o runner o entrega ao `judge`.
2. `test_id` do manifesto é o id completo do pytest (`tests/test_x.py::test_nome`).
3. `Measurer.judge` ganha um parâmetro opcional com os critérios e o manifesto declarado.
4. Só `FAILED` conta como vermelho. `ERROR` (importação, coleta, fixture) reprova a tentativa com a mensagem do pytest. O parser não guarda o tipo da exceção; fica fora do escopo.
5. Congelamento: `path → sha256` dos arquivos TEST e FIXTURE da etapa 1 no payload de `STAGE COMMITTED`; acima de 4096 bytes, só o digest mais um artefato `TEST_MANIFEST`. Calculado também na ramificação de retomada.
6. Os checks novos ficam no gate 5, registrados antes do `TestsCheck`, com entradas novas em `CheckSettings`.

## 6a — manifesto e vermelho/verde

1. `LlmOutput.tests` e leitura em `_declared`; o runner entrega o manifesto ao `judge` (parâmetro novo, opcional, padrão vazio, para não quebrar os outros chamadores). Testes de esquema e de leitura.
2. Parser: manter o texto depois do " - " apenas se for preciso para a mensagem de rejeição (decidir ao implementar; sem mudar o valor de `test.outcome`).
3. `RedGreenCheck` para a etapa do autor (só monta quando `task.role` é `TEST_AUTHOR`): (a) todo critério do `criterios.json` aparece em ao menos um `CriterionTest` do manifesto; (b) todo caminho do manifesto existe e é arquivo de teste; (c) roda só os testes novos (`test_files`) e cada teste do manifesto deve estar `failed`; um que passa é rejeitado com o nome; `error` ou ausente da saída reprova com a mensagem; (d) os testes que já existiam e passavam na base continuam passando (reaproveita `passing`).
4. Etapa do implementador: um check verde roda os testes do manifesto (ids congelados) e exige `passed`, além dos checks de hoje.
5. Entradas em `CheckSettings`/política; teste do pipeline com a ordem correta.
6. Testes contra os "testes ruins" do passo 2 (sem asserção, `assert True`, não chama o código, erro de importação, passa com e sem o defeito) e contra o teste bom.

## 6b — congelamento

1. Calcular `path → sha256` dos arquivos TEST e FIXTURE do commit da etapa 1 (`core\manifest.py`: `build_manifest`, `diff_manifests`), antes de remover o worktree; gravar no payload de `STAGE COMMITTED` (com a regra do teto), também na ramificação de retomada.
2. `FreezeCheck` na etapa 2: relê o congelado com `transition_payload` e compara com o worktree; alterar, apagar ou renomear arquivo congelado reprova, com o caminho. Gate 1 ou junto do escopo (decidir ao implementar; o gate mais barato possível).
3. Testes: alterar, apagar, renomear, adicionar arquivo novo de teste (permitido ou não: **a decidir**, ver pergunta abaixo) e retomada nas fronteiras novas (`test_resume_end_to_end.py`).

## Pronto quando

Cada teste ruim do passo 2 é rejeitado com a causa certa; o teste bom é aceito; a etapa do implementador só avança com o manifesto verde; mexer em arquivo congelado reprova; retomada por corte termina no mesmo estado; `ruff`, `mypy src tests` e testes rápidos verdes.

## Pergunta aberta

7. Na etapa do implementador, criar um arquivo de teste novo (fora do congelado) já é barrado pelo `ScopeCheck` (só produção). Então o congelamento só cobre modificar, apagar e renomear. Confirma que não há caso em que o implementador pode adicionar teste?

## Desvios do 6a em relação ao plano (13/10)

- O `RedGreenCheck` roda a suíte inteira (uma execução), em vez de só os arquivos novos com `test_files`: assim o mesmo resultado cobre os testes declarados, os antigos e qualquer teste não declarado que falhe. Ele **substitui** o `TestsCheck` na etapa do autor (o `TestsCheck` reprovaria os testes vermelhos de propósito).
- O item 4 (check verde do implementador) não foi criado: o `TestsCheck` já exige tudo verde, incluindo os testes commitados na etapa 1, e o congelamento (6b) impede apagar ou alterar esses testes.
- Erro de coleta: o pytest o relata sob o caminho do arquivo; o check o trata como "errors out" para o teste declarado daquele arquivo.
- Novo ponto de extensão: `AgentRunner.declared_tests(ctx)` e `Measurer.judge(..., expectations)`.
