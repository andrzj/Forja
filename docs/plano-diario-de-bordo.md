# Plano: diário de bordo

Item 5A da fila, depois do item 5 (gate 11). Origem: avaliação da skill `ub-mode` (`unclebob/ub-mode`, seção "Keep a Log" e "Attack the Premise") contra o que a Forja já faz. Ordem do dono, 27/10/2026.

## Problema

Cada chamada a um agente é nova e recebe só a última rejeição da etapa (`TaskCycle._last_rejection`, `build_package`). O agente não sabe o que as tentativas anteriores fizeram nem por que falharam. Duas consequências:

1. Duas tentativas que partem da mesma hipótese e falham no mesmo gate se repetem sem que ninguém, nem o agente, nem a Forja, veja o padrão.
2. O revisor humano só vê o motivo final de cada rejeição, no resumo, e não a sequência do que foi tentado.

## Decisões do dono

1. O diário vive no estado da Forja (o log de eventos) e na branch da tarefa.
2. Entra depois do item 5.
3. "Subtract Before You Add" fica de fora. Reavaliar na calibração (fila 6 ou 7), como uma linha no papel de refatorar e com uma métrica de observação (variação líquida de linhas de produção).
4. Worktree Cleanup e Commit and Push, da skill, ficam de fora (a Forja já gerencia worktrees e nunca faz push, ADR 0013).
5. Nenhum campo novo no contrato de saída do LLM. A hipótese comum a duas tentativas que falharam é escrita pelo agente no `reason` de `actions` (já obrigatório). Nas instruções chama-se **hipótese**, não premissa: `Assumption` e `PREMISE` já têm outro sentido na Forja.

## O que já existe (lido no passo 0 do pedido, 27/10/2026)

- O log guarda por tentativa: o que o agente disse (payload de `VALIDATING`, `task_cycle.py:362`), o motivo da rejeição com gate e achados (`describe_stop`, `REJECTED`), os gates aprovados (`APPROVED`) e a atividade (`agent_activity`: texto cortado em 200 caracteres, edições, comandos).
- `summary.py::read_facts` já projeta o log em texto e dá o mesmo resultado após retomada. O diário segue o mesmo modelo.
- `Journal.note` grava um evento `progress` de qualquer `kind`; `_check_progress` só restringe `process_started`; a UI ignora os `kind` que não conhece (já ocorre com `premise` e `trace`). Eventos `progress` não fazem `fsync`; os de transição fazem.
- `ScopeCheck._documenter` recusa arquivo em `docs/mudancas/` que não seja o registro da tarefa. A deriva isenta `docs/mudancas/`. O `ChangeRecordCheck` lê só o arquivo do registro. O gate de voz julga as linhas adicionadas de toda documentação e, no código, está em observação.
- Testes que fixam o texto do pacote: `tests/executors/test_package.py` (a seção "The previous attempt was rejected"), `tests/orchestrator/test_phases.py`, `test_untested_return.py`. A seção existente não muda.

## Passos

Um passo por commit. Cada commit atualiza o Registro de andamento do Plano de execução.

**Passo 0. Leitura e correções.** Ler o que este plano ainda não cobre e registrar "Correções do passo 0" aqui: `phases.py` (fechamento e escrita do resumo), `ui` (consumo de notas, só para confirmar), como o `claude_code` trata skills e `CLAUDE.md` do usuário (`--setting-sources user`; só uma chamada real decide, que é do item 8: registrar como limite), onde os marcadores de voz são bloqueantes (a Especificação, linha 292, diz que são; `specs.py:61` põe `voice` em observação). Fixar os limites iniciais do trecho do diário no pacote (resolve em parte a questão 7 da Especificação, só para este trecho).

**Passo 1. Projeção do log.** `orchestrator/diary.py`: função pura do `RunState` mais as notas para entradas por tarefa e etapa. Cada entrada tem papel, CLI, tentativa, o que o agente disse, o desfecho (rejeitada com gate e achados, aprovada com gates, descartada por infraestrutura) e as decisões da Forja (devolvida ao autor de testes, etapa esgotada, tarefa bloqueada, integração desfeita). Determinística: execução retomada dá o mesmo texto. Ainda não ligada. Testes com logs montados, inclusive log cortado.

**Passo 2. O agente vê o histórico.** `AttemptContext.diary` (padrão vazio, como `readme` e `adr`), preenchido em `TaskCycle`. Em `build_package`, seção "Earlier attempts of this stage" a partir da segunda tentativa, passando pelo redator (ADR 0009), com as últimas N entradas completas e as anteriores em uma linha, dentro do limite do passo 0. A seção "The previous attempt was rejected" fica como está.

**Correção (01/11/2026, ordem do dono):** o passo 2 acima, as "últimas N entradas completas e as anteriores em uma linha, dentro do limite do passo 0", saiu. O diário completo vai para o arquivo `.forja-agent\diary.md` do pacote (redigido, edição negada, conferência de adulteração em `apply_diff`); a seção "Earlier attempts of this stage" traz só a ordem imperativa de lê-lo antes de agir, e a seção da rejeição mais recente traz o motivo e a fala daquela tentativa, inteiros. Somem `LINE_CUT`, `DIARY_LIMIT`, `FULL_ENTRIES`, `cut()` e o `DIARY_CUT` do resumo.

**Passo 3. Gatilho da hipótese.** Quando o log mostra duas ou mais rejeições da mesma etapa no mesmo `gate N (check)`, o pacote ganha o texto de "Attack the Premise" (fiel à skill, trocando "premise" por "hypothesis") e o pedido de escrever a hipótese em uma frase no `reason` da ação. O detector e o texto ficam no mesmo módulo. Testes: uma rejeição não dispara; duas no mesmo gate disparam; duas em gates diferentes não disparam.

**Passo 4. Resumo.** Seção "Diário de bordo" no `resumo.md` com o nível da execução (base, planejamento, tarefas bloqueadas e o que foi tentado em cada uma). É o relatório do diário ao fim.

**Passo 5. Cópia no ramo.** `docs/mudancas/<tarefa>-diario.md`, escrito pela Forja junto com o registro, no commit `docs:` do documentador. Texto montado pela Forja a partir de campos do log, com o dito pelo agente truncado, para não depender do gate de voz. **[Superado: a fala não é truncada; ver as correções 7a e 7b.]** Muda: `ScopeCheck._documenter` (aceita o arquivo do diário da própria tarefa) e a Especificação (linha 531, "tentativas rejeitadas nunca viram commit", e linha 580, resumo fora do histórico): o diário registra as rejeitadas como texto, sem commit de código delas. Checar que voz, deriva e `change_record` continuam verdes com o arquivo.

**Passo 6. Fecho.** `docs\guia\diario-de-bordo.md` (o que o diário contém, onde fica, limites), ADR 0031, gate de mutação (`scripts\mutate.py`) nos arquivos novos e alterados, suíte rápida, `ruff` e `mypy src`.

## Fora de escopo

- Campo novo no contrato de saída do LLM.
- Instruções genéricas da skill (TDD, Laziness, Refactoring, Test Behavior): cada uma já tem gate.
- "Subtract Before You Add" (decisão 3).
- Guardar o diário entre execuções. Cada execução tem o seu, como os fatos.
- Qualquer LLM resumindo o diário: o corte é por regra determinística.

## Pendências registradas

- Divergência entre a Especificação (marcadores de voz bloqueantes por padrão) e `specs.py:61` (`voice` em observação). Decidir no passo 0 ou na fila 7.
- Se skills ou `CLAUDE.md` do usuário entram na chamada do Claude Code: só uma chamada real responde (item 8, do dono). Até lá, o efeito medido do diário pode se misturar com o de instruções do perfil.

## Correções do passo 0 (28/10/2026)

Lido: `orchestrator\phases.py` inteiro, `agent_runner.py::build_package` (linhas 335 a 372), `task_cycle.py` (limites de texto), `executors\claude_code.py::plan_invocation`, `checks\specs.py`, `ui\view.py` (consumo de `kind`), Especificação (linhas 287 a 292, 531 e 580).

1. **ADR.** O ADR do diário é o **0031**; o 0030 é do gate 11. O passo 6 diz 0030: corrigido para 0031.
2. **Onde o diário entra.** `Orchestrator._close` já chama `read_facts(log.path)` e `render_summary` (`phases.py:276`); o passo 4 acrescenta a seção dentro de `render_summary`, sem tocar em `phases.py`. O diário é projeção do log, como o resumo: não precisa de caminho novo de escrita e dá o mesmo texto após retomada. Nenhuma mudança em `phases.py`.
3. **Pacote.** `build_package` monta o pacote em seções e a rejeição anterior é a última (`agent_runner.py:370`). A seção nova "Earlier attempts of this stage" entra logo **antes** dela, para a rejeição mais recente continuar sendo a última coisa que o agente lê. O texto existente não muda.
4. **UI.** `ui\view.py` trata `kind` por `if/elif` e ignora o que não conhece (`premise` e `trace` já passam assim). O diário não grava `kind` novo: é projeção do log existente (passos 1 a 4). Só o passo 5 grava arquivo, e não é nota.
5. **Skills e `CLAUDE.md` do usuário.** A chamada usa `--setting-sources user` e `--disable-slash-commands`. O segundo desliga os comandos de barra e as skills invocadas por eles; o primeiro lê a configuração do usuário, e se o `CLAUDE.md` global entra na chamada só uma chamada real diz. **Limite registrado** (item 8, do dono): o efeito medido do diário pode se misturar com o de instruções do perfil.
6. **Voz.** A Especificação (linha 292) diz que a lista de marcadores é bloqueante por padrão; `specs.py` põe `voice` em `OBSERVATION` com `PREMISE`, sob a regra da linha 288 (check novo começa em observação). **Decisão:** não muda aqui. Fica para a fila 7 (promoção de gates), onde a Especificação ou a política se emenda. Consequência para o passo 5: o arquivo do diário passa pelo `VoiceCheck` só em observação.
7. **Limites do trecho do diário no pacote (decisão minha, reversível; só para este trecho, não fecha a questão 7 da Especificação).** Entram só tentativas da **mesma etapa**, anteriores à atual. As **3 últimas** vão completas: papel, tentativa, o que o agente disse (cortado em 300 caracteres), desfecho (rejeição com gate e achados, cortada em `REASON_LIMIT`, 1500). As **anteriores** vão em uma linha de até 160 caracteres (tentativa, gate, motivo curto). O trecho inteiro tem teto de **6000 caracteres**: passando disso, caem primeiro as linhas das mais antigas, depois as completas mais antigas, nunca a rejeição anterior (que tem seção própria). Corte por regra, sem LLM.
7a. **Correção do item 7 (28/10/2026, ordem do dono; as linhas de 160 e o teto de 6000 foram retirados em 01/11/2026, ver a correção do passo 2).** A fala do agente não é mais cortada em 300 caracteres: entra inteira e como foi escrita (várias linhas vão citadas com `> `). Regra: toda entrada ao modelo é fiel, fidedigna e verdadeira. As linhas únicas das mais antigas (160) e o teto de 6000 seguem, sempre declarados no texto. No resumo o corte é de 1500.
7b. **Passo 5 (28/10/2026, decisão minha, reversível).** A cópia no ramo não trunca a fala do agente nem o motivo: ambos chegam inteiros (o `REASON_LIMIT` de 1500 saiu na fila 12, 01/11/2026) e vão citados com `> `, como estão no log. Isso vale a regra de fidelidade do 7a; o plano pedia fala truncada para não depender do gate de voz, que segue em observação (item 6). Entram todas as tentativas de todas as etapas da tarefa, menos a do documentador que está sendo julgada, e as decisões da Forja. Sem tentativa nem decisão, o arquivo diz “Nenhuma tentativa anterior.”. A linha 580 da Especificação (resumo não commitado) continua valendo e não foi emendada.
8. **Tentativa descartada por infraestrutura** (`infra_failure`) entra no diário em uma linha e não conta como tentativa para o gatilho do passo 3.
