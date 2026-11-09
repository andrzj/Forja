# Plano: cache de medições, executor de mutação e calibração

Item 6 da fila. Três partes; a A foi suprimida por ordem do dono (abaixo).

## Estado lido no passo 0 (29/10/2026)

- `core\evidence\cache.py` tem `cache_key(MeasurementContext)` e `EvidenceCache` (índice em memória sobre o `EvidenceStore`), e a chave segue o contrato 5 e o ADR 0010. **Nada fora de `core` os usa**: nenhum código produz `Evidence` nem `MeasurementContext`. Os checks rodam ferramentas por `checks\base.py::measure_plan` → `checks\tooling.py::Tools.run(check, plan)`, que sempre cria processo novo. O passo 1 do 3e em `plano-3.md` (“onde o medidor mede sem consultar o cache”) tem, portanto, a resposta: em todo lugar.
- `CommandPlan` (`core\adapters\common.py`) já separa `argv`, `cwd`, `env_allow`, `env_set`, `stdin_file` e `config_files`; o docstring diz que o conteúdo de `config_files` entra no hash de configuração. A versão da ferramenta e a da toolchain não estão no plano de comando.
- `mutation\executor.py`: o gate de mutação (`scripts\mutate.py`) rodou nele em 29/10 e **não achou sobrevivente** (um arquivo de teste o exercita). Os “4 sobreviventes” da fila não aparecem em nenhum documento nem no gate; o registro vinha de uma rodada anterior já fechada ou de uma contagem que se perdeu.
- Calibração: a Especificação (linhas 288 e 404) e o Plano mandam calibrar os limiares com dados de revisão. Esses dados vêm de `forja revisao` sobre execuções reais revisadas pelo dono; não há nenhum relatório desses no repositório.

## Parte A. Cache de medições pela chave completa (3e): suprimida

**Ordem do dono, 29/10/2026:** o 3e foi superestimado. Não se constrói agora; com a Forja pronta e em uso, os dados dizem se há repetição de medição que justifique (repetição idêntica na retomada, mutação e CRAP rodando os mesmos testes). Enquanto isso valem `cache_key` e `EvidenceCache` como estão em `core`, sem consumidor. Se for retomado, o desenho está no que se leu no passo 0: a ligação cabe em `Tools.run`, a chave pode precisar do hash do conteúdo medido em vez do `HEAD`, e medição que repete de propósito (teste instável, diferencial, E2E, mutação por arquivo) fica fora.

## Parte B. Executor de mutação

Nada a construir. **B1.** Registrar no Plano que o gate rodou em `mutation\executor.py` e deu zero sobreviventes (29/10/2026), e tirar o item da fila. Se uma rodada futura achar sobrevivente, vira passo novo.

## Parte C. Calibração dos limiares

Depende de dado que a Forja não produz sozinha: execuções reais revisadas. **Do dono.** O que a Forja pode fazer sem esse dado, e só isso:

**C1.** Listar os limiares ainda sem dados (mutação 0,80 e 0,70; complexidade; pass-through e profundidade; `max_distance` e `min_types`; `max_time_ratio` e `max_memory_ratio`; `max_dashes`) com o valor atual, o gate e a fonte do número, em um documento (`docs\guia\forja-toml.md`). Sem alterar nenhum valor.

**C2.** Quando o dono tiver relatórios de `forja revisao` de execuções reais, calibrar com eles e promover gates de observação para bloqueante por decisão registrada na política. Isso é o item 7 da fila (promoção de gates) e fica parado até haver o dado; o Plano registra o bloqueio.

## Fora de escopo

Cache entre execuções (ADR 0010); inventar dado de revisão; mudar qualquer limiar sem dado.
