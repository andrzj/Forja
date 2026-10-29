# Plano: cache de medições, executor de mutação e calibração

Item 6 da fila. Três partes que não dependem entre si; a ordem abaixo é a de execução.

## Estado lido no passo 0 (29/10/2026)

- `core\evidence\cache.py` tem `cache_key(MeasurementContext)` e `EvidenceCache` (índice em memória sobre o `EvidenceStore`), e a chave segue o contrato 5 e o ADR 0010. **Nada fora de `core` os usa**: nenhum código produz `Evidence` nem `MeasurementContext`. Os checks rodam ferramentas por `checks\base.py::measure_plan` → `checks\tooling.py::Tools.run(check, plan)`, que sempre cria processo novo. O passo 1 do 3e em `plano-3.md` (“onde o medidor mede sem consultar o cache”) tem, portanto, a resposta: em todo lugar.
- `CommandPlan` (`core\adapters\common.py`) já separa `argv`, `cwd`, `env_allow`, `env_set`, `stdin_file` e `config_files`; o docstring diz que o conteúdo de `config_files` entra no hash de configuração. A versão da ferramenta e a da toolchain não estão no plano de comando.
- `mutation\executor.py`: o gate de mutação (`scripts\mutate.py`) rodou nele em 29/10 e **não achou sobrevivente** (um arquivo de teste o exercita). Os “4 sobreviventes” da fila não aparecem em nenhum documento nem no gate; o registro vinha de uma rodada anterior já fechada ou de uma contagem que se perdeu.
- Calibração: a Especificação (linhas 288 e 404) e o Plano mandam calibrar os limiares com dados de revisão. Esses dados vêm de `forja revisao` sobre execuções reais revisadas pelo dono; não há nenhum relatório desses no repositório.

## Parte A. Cache de medições pela chave completa (3e)

Pronto quando: medição repetida com a chave inteira igual não cria processo (provado por contagem de processos); mudar qualquer componente da chave refaz; a evidência reaproveitada fica marcada no log. Reaproveitar errado é pior do que refazer.

**A1. Leitura e correções.** Ler `PipelineMeasurer` (de onde vêm `head` e a worktree em `judge` e `baseline`), a fachada de git, como o diretório da execução guarda evidências e como o adaptador diz a versão da ferramenta e da toolchain. Registrar “Correções” aqui. Duas coisas a decidir lendo, não perguntando:
1. **O que é “commit” quando a worktree tem mudança ainda não commitada.** O `judge` mede o trabalho da tentativa antes do commit; se o `HEAD` for o do commit pai, a chave não distingue duas tentativas diferentes. Se for o caso, a chave leva o hash do conteúdo medido (árvore de arquivos), não o `HEAD`.
2. **Quais medições se repetem de propósito** e não podem ser reaproveitadas: o teste instável, o diferencial (`runs` execuções), o E2E em repetição, a mutação por arquivo. O cache é por chamada de `Tools.run` e liga só nas que o check marca como determinísticas.

**A2. A chave.** Função que monta `MeasurementContext` de `CommandPlan` + conteúdo medido + versão da ferramenta e da toolchain + plataforma. `config_hash` cobre `argv`, `env_set`, `cwd` relativo, o conteúdo de `config_files` e o limite de tempo (ele muda o resultado). Escopo = os arquivos ou o diretório medido. Versões obtidas por sonda, uma vez por execução.

**A3. Ligação.** `Tools.run` consulta antes e grava depois, só para execuções que terminaram sozinhas (`EXITED`); estouro de tempo, falha ao iniciar e parada nunca entram. Acerto devolve o `Execution` da execução original (mesmo log e mesmo `operation_id`) e grava uma nota no log com o `operation_id` de origem, para o resumo e a retomada saberem. O cache vale dentro da execução (ADR 0010).

**A4. Testes por componente.** Segunda medição idêntica: zero processos. Para cada componente (conteúdo, `argv`, `env_set`, `config_files`, versão da ferramenta, toolchain, plataforma, escopo, limite de tempo): mudar só ele refaz. Execução que estourou o tempo não é reaproveitada. Retomada: o índice relido do disco dá o mesmo acerto.

**A5. Fecho.** `docs\` (como o cache funciona e o que ele não reaproveita), nota ao ADR 0010 ou ADR novo se a decisão de A1 mudar a chave, gate de mutação nos arquivos novos, suíte rápida, `ruff`, `mypy src`.

## Parte B. Executor de mutação

Nada a construir. **B1.** Registrar no Plano que o gate rodou em `mutation\executor.py` e deu zero sobreviventes (29/10/2026), e tirar o item da fila. Se uma rodada futura achar sobrevivente, vira passo novo.

## Parte C. Calibração dos limiares

Depende de dado que a Forja não produz sozinha: execuções reais revisadas. **Do dono.** O que a Forja pode fazer sem esse dado, e só isso:

**C1.** Listar os limiares ainda sem dados (mutação 0,80 e 0,70; complexidade; pass-through e profundidade; `max_distance` e `min_types`; `max_time_ratio` e `max_memory_ratio`; `max_dashes`) com o valor atual, o gate e a fonte do número, em um documento (`docs\limiares.md`). Sem alterar nenhum valor.

**C2.** Quando o dono tiver relatórios de `forja revisao` de execuções reais, calibrar com eles e promover gates de observação para bloqueante por decisão registrada na política. Isso é o item 7 da fila (promoção de gates) e fica parado até haver o dado; o Plano registra o bloqueio.

## Fora de escopo

Cache entre execuções (ADR 0010); inventar dado de revisão; mudar qualquer limiar sem dado.
