# Forja — plano de execução

## Como este documento governa o trabalho

Este é o documento que mantém a construção da Forja nos trilhos. As regras abaixo valem para qualquer pessoa ou LLM que trabalhe no projeto e mandam sobre notas de sessão e preferências de momento.

1. **Reler antes de toda demanda.** Antes de começar qualquer trabalho, o LLM lê este documento inteiro (regras, **Fila obrigatória** e as dez entradas mais recentes do **Registro de andamento**). Nenhuma demanda começa sem essa leitura, mesmo as que pareçam pequenas. O arquivo `docs\registro-arquivo.md` guarda as entradas antigas e só se consulta sob demanda, por busca, nunca inteiro. Ao entrar uma entrada nova no Registro, a mais antiga das dez passa para o arquivo no mesmo commit.
2. **O LLM não escolhe o que fazer.** O trabalho é o do primeiro item da Fila obrigatória que não está concluído, feito por inteiro e na ordem dos passos do plano daquele item. Pular item, antecipar item posterior, acrescentar escopo ou trocar a ordem só com ordem expressa do dono, e a ordem é registrada aqui antes de seguir. Gate ou componente que ninguém alimenta ainda não se constrói à frente do que o alimenta.
3. **Demanda fora da fila.** Se o dono pede algo que não é o próximo item, o LLM diz qual é o próximo item da fila, executa o que foi pedido apenas se for ordem expressa e registra no Registro de andamento que a fila foi alterada e por quê.
4. **Toda atualização do projeto é registrada aqui, no mesmo commit que a causou:** passo concluído, plano escrito, decisão do dono, mudança de ordem, pendência nova. O registro diz data, o que mudou e os commits. O estado da fila (concluído, em andamento, a fazer) é atualizado junto.
5. **Plano antes de código** quando o item toca vários módulos: o plano vai em `docs\plano-<item>.md`, referenciado na fila, e só então se constrói, um passo por commit.
6. **O que fica de fora de todos os itens:** qualquer coisa que a Especificação põe em "Fora de escopo". Os testes E2E reais **não** ficam mais de fora nem são do dono: por ordem expressa do dono (08/11/2026), o LLM os executa, conforme a fila 18 e `docs\plano-e2e.md`. Onde a fila, o Registro e os planos dizem "E2E real, que é do dono", leia-se "fila 18".
7. **Divergência.** Se a Especificação e este documento divergem, vale a Especificação; o LLM aponta a divergência e corrige este documento.
8. **Estados da fila.** Só estes: **a fazer**, **em andamento**, **concluído**, **do dono** e **dispensado**. "Parado" não existe: item que espera dado ou ordem do dono é **do dono**; o que o dono tirou da construção é **dispensado**, com data e motivo no Registro, e não é pendência de ninguém. O que falta de um item concluído (E2E real) fica dito na própria linha, como do dono.
9. **Escrever caminhos.** Caminhos do Windows levam barra invertida (`core\adapters`). Escrever neste documento pela ferramenta de edição, nunca por script com `\a`, `\f`, `\n`, `\r`, `\t` ou `\v` em texto comum: o interpretador os troca por caracteres de controle e quebra o caminho. Depois de editar, `grep -P '[\x00-\x08\x0b-\x1f]'` não pode achar nada.
10. **Antes de dizer o que falta.** O LLM lista pendência só a partir da fila, do Registro e do `NOTAS.md`, na ordem deste documento; se os três divergem, vale o Registro e a divergência é apontada.

## Fila obrigatória

Ordem fixa. O próximo trabalho é sempre o primeiro item não concluído. Cada item cita o plano que o detalha.

| # | Item | Plano | Estado |
| --- | --- | --- | --- |
| 1 | Gate 6, fecho: documentação do usuário e ADR (passo 6) e gate de mutação nos arquivos novos. O E2E real é do dono. | `docs\plano-gate-6.md` | **concluído** (23/10); falta só o E2E real, que é do dono |
| 2 | Incremento 4: documentador (registro de mudança, README, ADR por regra, deriva, voz, citações do documentador, resumo) | `docs\plano-documentador.md` | **concluído** (24/10): passos 0 a 10 |
| 3 | Incremento 6: especificador (critérios, rastreabilidade, `manifesto-testes.json`), arqueólogo, andaime, modo de diretório vazio, premissas e fatos completos, coleta da revisão, gate 13 completo | `docs\plano-especificador-arqueologo.md` | **concluído** (26/10): passos 0 a 8; falta só o E2E real, que é do dono |
| 4 | Incremento 5, restante: gate 9 (arquitetura) | `docs\plano-gate-9.md` | **concluído** (27/10): passos 0 a 8; falta só o E2E real, que é do dono |
| 5 | Incremento 5, restante: gate 11 (teste diferencial); depende do item 3 | `docs\plano-gate-11.md` | **concluído** (28/10): passos 0 a 9; falta só o E2E real, que é do dono |
| 5A | Diário de bordo: o agente vê o histórico das tentativas, gatilho da hipótese comum a rejeições repetidas, seção no resumo e cópia no ramo (origem: skill `ub-mode`). Depende do item 5 | `docs\plano-diario-de-bordo.md` | **concluído** (29/10): passos 0 a 6; falta só o E2E real, que é do dono. Ordem do dono: depois do item 5 |
| 6 | Incremento 3, restante: ~~3e (cache de medições)~~ **suprimido por ordem do dono (29/10), a reavaliar com a Forja em uso**; os 4 sobreviventes de `mutation\executor.py` (zero no gate de 29/10: nada a fazer); ~~calibração dos limiares com dados de revisão (C2)~~ **dispensada pelo dono (31/10)** | `docs\plano-medicoes-e-calibracao.md` | **concluído** (31/10): passo 0 e C1 feitos (29/10 e 30/10); C2 dispensado, não é pendência |
| 7 | Incremento 7: endurecimento (paralelismo, mutação incremental, modo CI, adaptador genérico, documentação de uso, inclusive a sugestão de CLIs diferentes entre papéis); ~~promoção de gates (passo 8)~~ **dispensada pelo dono (31/10)** | `docs\plano-endurecimento.md` | **concluído** (31/10): passos 0 a 7 e fecho (gate de mutação nos arquivos novos); passo 8 dispensado, não é pendência; falta só o E2E real, que é do dono |
| 8 | Fecho: ~~3f (aceitação e repetição do experimento com duas CLIs reais)~~ **fora do escopo (31/10)**, execução viva com o Claude Code, E2E real, fixtures e testes `live` | | **concluído** (31/10): só Claude Code; E2E real feito (execuções 3 e 4 entregaram); outras CLIs e 3f com duas CLIs fora do escopo |
| 9 | Correção do `IntegrationConflict`: merge da tarefa que não aplica hoje derruba a execução (exceção não capturada em `task_cycle.py`/`phases.py`); passa a bloquear a tarefa (`BLOCKED`, `reason` de conflito), com a worktree da execução limpa e as outras tarefas seguindo. Testes em memória e com git real, também com `paralelismo` acima de 1. Corrigir ao mesmo tempo o texto errado dos registros 6b e de `docs\plano-paralelismo.md`, e `docs\paralelismo.md` e o ADR 0032 | | **concluído** (31/10): feito antes da fila 8 por ordem expressa do dono; falta só o E2E real, que é do dono |
| 10 | Voz como instrução, nunca como bloqueio: a Forja controla a escrita dos agentes na origem (pacote, e arquivo de instruções, regras ou skill onde a CLI permitir; referência: skill `humanizer`); o gate 12 só mede e reporta | `docs\plano-voz.md` | **concluído** (31/10), passos 0 a 5; resta o E2E real do dono (efeito da voz); ordem expressa do dono (31/10) |
| 11 | Dependências que o agente pode adicionar: o gate 1 aceita manifesto, as instruções trocam a proibição pela regra de necessidade (DRY), e no Python a Forja cria um ambiente virtual isolado por execução, depois de conferir no registro que a dependência existe | `docs\plano-dependencias.md` | **concluído** (01/11): passos 1 a 6 feitos; falta só o E2E real, que é do dono; ordem expressa do dono |
| 12 | Limites conhecidos: ambiente com instalação editável, barra de gates 9 a 11, redação do diário no ramo, gate 11 em Linux e macOS, teste de queda após `BLOCKED`, comentário de `crap.py`, fim do `REASON_LIMIT`; antes, gate de mutação no diário e nos sobreviventes antigos. Fora: guarda de git com `paralelismo` acima de 1 (dono: deixar como está) | `docs\plano-limites.md` | **concluído** (02/11): passos 1 a 7 e o gate de mutação antes e depois; ordem expressa do dono; falta só o E2E real, que é do dono |
| 13 | Gate de duplicação (DRY): `jscpd`, previsto na Especificação (linha 400) e não implementado; catraca, modo observação, instruções ao agente, documentação e ADR | `docs\plano-gate-duplicacao.md` | **em andamento** (03/11): passos 0 a 7 feitos; E2E (passo 8) é do dono; ordem expressa do dono |
| 14 | Instalação das ferramentas externas: a Forja instala as ferramentas de terceiros de que precisa (sempre OSS) e o usuário passa a ter uma instalação da Forja, em vez de preparar o ambiente à mão | `docs\plano-instalacao.md` | **em andamento** (02/11): passos 0 a 9 feitos; E2E em máquina limpa (passo 10) é do dono; ordem expressa do dono |
| 15 | Análise estática de tipos por linguagem, com o critério do dono (03/11): barata, confiável e, se externa, OSS. Avaliado: TypeScript (`tsc` no build), Java (`javac` mais SpotBugs, PMD e Checkstyle), Go (compilador, `go vet` e golangci-lint) e C# (compilador e analisadores Roslyn) já têm; Python só tem `ruff`, e o `mypy` (MIT) passa no critério. A fazer: check de tipos do Python na catraca do lint (erro novo em relação à base), `mypy` com `--python-executable` do repositório para resolver as dependências dele. Plano escrito antes do código | `docs\plano-analise-estatica.md` | **em andamento** (06/11): plano escrito, passos 0 a 5 feitos; E2E (passo 6) é do dono; ordem expressa do dono; as filas 13 e 14 só esperam o E2E do dono |
| 16 | Teste de propriedades para todas as linguagens suportadas, quando fizer sentido: ferramenta OSS por linguagem (barata e confiável), instrução ao agente, papel no fluxo, gate e documentação. Plano a escrever, com leitura das ferramentas por inteiro (regra 2 do projeto), antes do código | `docs\plano-teste-de-propriedades.md` | **em andamento** (06/11): plano escrito, passos 0 a 6 feitos (Java com QuickTheories, decisão do dono); E2E (passo 7) é do dono; ordem expressa do dono |
| 17 | Melhorias da interface de terminal que a Especificação pede: teclas `d` (detalhes da tarefa atual) e `l` (atividade inteira), `q` interrompe com segurança, barra agrupada pelos gates 1 a 12, tokens da tarefa atual no cabeçalho | `docs\plano-ui.md` | **concluído** (08/11): passos 0 a 6; falta só o E2E real (ver as telas numa execução), que é do dono; ordem expressa do dono |
| 18 | E2E reais de todas as filas pendentes (1, 4, 5, 5A, 10, 12 a 17), executados pelo LLM: rejeição dos gates 6, 9 e 11, SAST e OSV, voz, diário no ramo, instalação editável, `jscpd`, `mypy`, propriedades, instalação em diretório limpo (Windows e WSL), gate 11 em Linux e as telas da UI | `docs\plano-e2e.md` | **a fazer** (08/11): plano escrito; ordem expressa do dono |

## Registro de andamento

Mais recente primeiro. Cada linha: data, o que mudou, commits.

Entradas anteriores às dez abaixo: `docs\registro-arquivo.md` (só leitura, consultar sob demanda; não é para ler inteiro em toda sessão).

- **08/11/2026 (fila 18 criada, ordem expressa do dono: "refazer o plano para que você rode o E2E"):** o E2E real deixa de ser do dono. Regra 6 reescrita; fila 18 criada com todos os E2E pendentes das filas 1, 4, 5, 5A, 10, 12 a 17; plano em `docs\plano-e2e.md` (11 E2E, um por passo, repositório descartável fora de `forja\`, falha vira correção na Forja, WSL `Ubuntu-22.04` presente para Linux). Conferido nesta máquina: `claude` e `node` no PATH, `jscpd` ausente (a Forja instala). Nada executado. Próximo: passo 1 do plano (rejeição dos gates 6, 9 e 11).

- **08/11/2026 (correção fora da fila, pedida pelo dono):** `ui\panels.py::rejections` descontava 4 células fixas do prefixo; passa a descontar a largura real de `" {marks.failed} "`, então no tema ASCII (marca `[X]`) a linha cabe e termina em `…`. `tests\ui\panels_golden.json` regravado: só as 12 famílias de `rejections` mudaram. Gate de mutação em `ui\panels.py` (cobertura regravada): a primeira rodada parou com exit 2 em `test_differential_check.py::test_a_different_exit_code_rejects` (falha espúria sob carga, passa isolado, 20/20); repetida: "all mutants killed or suppressed". `tests\ui` (3531) e `ruff` limpos. Fecha a observação fora do escopo da entrada abaixo.
- **08/11/2026 (fila 17, passo 6 feito; fila 17 concluída):** gate de mutação (`scripts\mutate.py`, cobertura regravada) em `ui\view.py`, `ui\live.py`, `ui\panels.py`, `ui\full.py`, `ui\install_panels.py`, `ui\install_text.py`, `cli\keys.py` e `cli\run.py`. A primeira rodada parou com "the tests fail before any mutation" (`test_gate_11_measurer.py::test_an_attempt_that_changes_the_output_of_the_base_is_rejected` sob carga, instabilidade já registrada em 07/11); repetida. Segunda rodada: 18 sobreviventes e 10 sítios sem teste em `keys.py` (que não tinha teste); `full.py`, `run.py` e `keys.py` nunca tinham passado pelo gate. **Defeito meu achado:** no tema ASCII a linha de cada check dos detalhes passava da largura e terminava em `…` (a marca `[X]` tem 3 células e eu descontava 3 fixas); corrigido com a largura da marca. **Defeitos antigos corrigidos por estarem no caminho dos detalhes e do log:** `panels.py::_title` cortava com `…` em vez do `ellipsis` do tema; `_wrapped_lines` tira a hora quando não sobram 3 células para o texto. **Reescritos por serem equivalentes, sem suprimir:** `full.py::Pane.render` sem `max(..., 1)` (Textual não desenha painel de tamanho zero; conferido de 1x1 a 80x12 com `d`, `l` e `?`) e sem `no_wrap`/`overflow` na junção (toda linha já cabe); `_window` sem o `max(height, 1)`. Testes novos: `window` nos limites; detalhes curtos sem rolagem e topo igual a linhas menos altura; só os painéis que rolam pegam foco; o fim tira o aviso de parada; a tela cheia não roda `headless` por padrão; `run.py` (avisos só na entrega, "nenhuma integrada", tecla que conta mesmo com a execução terminando sozinha, segunda tecla depois do fim não força a saída); `keys.py` (leitura no Windows e em POSIX com módulos falsos, thread `daemon`, `close`, `terminal_keys`); detalhes e log sem `…` no tema ASCII. Terceira rodada: 2 sobreviventes em `keys.py`, mortos; `keys.py` de novo: "all mutants killed or suppressed". Nada suprimido. `ruff` e `mypy` (324 arquivos) limpos; `tests\ui`, `test_keys` e `test_run` (3558) passaram. **Observação fora do escopo:** `panels.py::rejections` desconta largura fixa da marca como os detalhes descontavam, e no tema ASCII deve terminar em `…`; não mexido. E2E real (ver as telas) é do dono.

- **08/11/2026 (fila 17, passo 5 feito):** tecla `l`. `ui\view.py`: `ViewModel.log` guarda, sem limite, toda linha que vai para a atividade (a da tarefa em tela, como o painel) e uma linha `mede <check> (gate N)` por check que começa a medir (`_tool` recebe a hora do evento); `View.log` a entrega. `ui\panels.py::log_lines` (puro): cada linha inteira, quebrada, com a hora; vazio diz isso. `ui\full.py`: painel `log` rolável sobre a execução, aberto no fim, no mesmo mecanismo do `d`. Rodapé e ajuda com `l`. Testes: `tests\ui\test_view.py` (log passa das 60 linhas do painel; check que começa; outra tarefa fica fora), `tests\ui\test_panels.py` (linhas inteiras com hora; vazio; largura e símbolos), `tests\ui\test_full.py` (abre no fim, rola, fecha, todos os tamanhos); golden com as famílias `log` e regravado. `ruff` e `mypy` (294 arquivos) limpos; `tests\ui` e `tests\cli` sem `slow` (3887) passaram. Próximo: passo 6 (gate de mutação nos arquivos mudados).

- **08/11/2026 (fila 17, passo 4 feito):** tecla `d`. `ui\panels.py::details` (puro): tarefa e tentativa, intenção inteira (quebrada em linhas), cada check com gate e estado (`gate  3 · lint`) e as rejeições da tarefa em tela sem corte (as de outras tarefas ficam fora); sem tarefa, diz isso. `panels.py::window` corta a parte visível. `ui\full.py`: painel `details` rolável sobre a execução, aberto no topo e com a rolagem presa entre a primeira e a última linha (`_window`); telas sobrepostas genéricas (`OVERLAYS`, `_toggle`): abrir uma fecha a outra, `d` de novo, `q` ou `esc` fecham, e só depois disso `q` para a execução. Rodapé e ajuda com `d`. `wrapped` saiu de `ui\install_panels.py` para `panels.py` (o instalador e `install_text.py` importam de lá, sem cópia). Testes: `tests\ui\test_panels.py` (conteúdo, rejeições de outra tarefa, sem tarefa, `window`, largura e símbolos com a vista nova), `tests\ui\test_full.py` (abre no topo, rola, fecha com `d`, `q` e `esc` sem parar, uma fecha a outra, em todos os tamanhos, depois do fim); golden com as famílias `details` e regravado. `ruff` e `mypy` (294 arquivos) limpos; `tests\ui` e `tests\cli` sem `slow` (3875) passaram. Próximo: passo 5 (tecla `l`).

- **08/11/2026 (fila 17, passo 3 feito):** tokens da tarefa atual no cabeçalho. `ui\view.py`: `ViewModel.task_tokens` soma cada evento `usage` na tarefa dona da tentativa (prefixo de `target_id`, como `_foreign`), e `View.task_tokens` traz o gasto da tarefa em tela; a retomada o refaz pelo `replay`. `ui\panels.py::_cost`: parte `· tarefa 120k` depois do total, só com tarefa em tela; quando falta largura cai antes do tempo (que a Especificação pede no cabeçalho), nunca antes dos tokens da execução. Testes: `tests\ui\test_view.py` (cada tarefa com seu gasto; a tela segue a tarefa; zero antes de gastar), `tests\ui\test_panels.py` (texto inteiro; a tarefa sai antes do tempo; sem tarefa, sem a parte); cenário `full` do golden com `task_tokens` e golden regravado (só as famílias `header`). `ruff` e `mypy` limpos; `tests\ui` e `test_run` (3490) passaram. Próximo: passo 4 (tecla `d`).

- **08/11/2026 (fila 17, passo 2 feito):** barra pelos gates 1 a 12. `ui\view.py`: `GATE_OF` (check para gate, igual a `checks\specs.py`) e `gate_groups` (reprovado se algum check reprovou; em andamento se algum roda; aprovado se todos passaram; pendente nos demais, porque `complexity`, do gate 8, roda antes de `mutation`, do 7). `ui\live.py::GATE_LABELS` (nomes dos gates em ASCII, porque os temas ASCII também os desenham: `mutacao`, `metricas`, `seguranca`); `panels.py::gates_line` passa de nomes para números e depois só símbolos; `live.py::_gates` usa os nomes. `GATE_NAMES` (nome curto de cada check) fica para os detalhes do passo 4. Testes: `tests\ui\test_view.py` (mapa igual ao registro; soma de estados; ordem dos gates), `tests\ui\test_panels.py` (três formas da barra), `tests\ui\test_live.py` (segunda linha; barra só ASCII com tema ASCII); golden regravado (famílias `gates` e `attempt`). Documentos do usuário que diziam que a barra não mostrava `types`, `duplication`, gate 9 e gate 11 corrigidos (`tipos.md`, `duplicacao.md`, `arquitetura-e-dependencias.md`, `teste-diferencial.md`). `ruff` e `mypy` limpos; `tests\ui` e `test_run` (3486) passaram. Próximo: passo 3 (tokens da tarefa no cabeçalho).

- **08/11/2026 (fila 17, passo 1 feito):** tecla `q` interrompe com segurança, como `ctrl+k` (que segue valendo, com `ctrl+c`): na tela cheia (`ui\full.py::action_quit_or_stop`: com a ajuda aberta, `q` a fecha; depois do fim, sai; senão, para, e o segundo `q` sai na hora), no leitor do terminal (`cli\keys.py::KEYS` com `q` e `Q`) e em `cli\run.py::_watch`. Textos: rodapé, faixa e ajuda de `ui\panels.py`, `ui\live.py::HINT` ("q interrompe"). Testes: `tests\ui\test_full.py` (`q` para e pede de novo; com a ajuda, só a fecha; no fim, sai sem pedir parada), `tests\cli\test_run.py` (`q` entre as teclas que param), `tests\cli\test_keys.py` (novo: cada caractere e seu nome; desconhecido é ignorado); larguras dos testes da dica em `test_live.py` e `test_live_exact.py` (a dica ficou menor) e `tests\ui\panels_golden.json` regravado (só mudaram as famílias de faixa, rodapé e ajuda). `ruff` e `mypy` limpos; `tests\ui`, `test_keys` e `test_run` (3481) passaram. Nenhum documento do usuário citava `ctrl+k`. Próximo: passo 2 (barra pelos gates 1 a 12).

- **08/11/2026 (fila 17 criada, ordem expressa do dono: "implemente as melhorias" da UI do `NOTAS.md`; plano escrito, passo 0):** as filas 13 a 16 só esperam o E2E do dono, então a fila 17 entra como próximo trabalho. Decisões do dono por pergunta: `d` mostra a tarefa atual inteira (checks com nome, gate e estado; rejeições sem corte); `l` mostra a atividade inteira, rolável; a barra mostra os gates 1 a 12 (13 e 14 são do documentador); o cabeçalho mostra os tokens da tarefa atual ao lado do total. Minhas, dentro da Especificação: `q` interrompe como `ctrl+k` (que continua valendo, com `ctrl+c`); `d` e `l` só na tela cheia. Plano em `docs\plano-ui.md`. Nada implementado. Próximo: passo 1 (tecla `q`).

- **07/11/2026 (fora da fila, ordem expressa do dono: nenhum sobrevivente fica vivo):** gate de mutação (`scripts\mutate.py`) nos arquivos com sobrevivente antigo. **Mortos com teste:** `languages\python\manifest.py` (2: nome de arquivo com marcador depois dele; arquivo de requisitos com linha continuada que não mudou; `tests\languages\test_manifests.py`), `cli\doctor.py` (17 sobreviventes e 12 sítios sem teste) e `cli\detect.py` (6 e 1) em `tests\cli\test_doctor_checks.py` e `tests\cli\test_detect_branches.py`; `checks\properties.py`, `checks\layout.py` e `core\dependencies.py` limpos (os 3 de `dependencies.py` e o de `layout.py` das rodadas de 06/11 eram de cobertura defasada ou instabilidade: em rodada limpa não aparecem). Confirmado em rodada independente com cobertura regravada do zero. `mypy` (606 arquivos) e `ruff` limpos. **Descobertas:** (1) `--reuse-coverage` só reaproveita o relatório quando há um, então teste novo exige regravar sem a flag; (2) a rodada completa de cobertura pode reprovar `tests\checks\test_gate_11_measurer.py::test_an_attempt_that_changes_the_output_of_the_base_is_rejected` sob carga (passa sozinho; uma vez `dependencies.py` parou por isso com "the tests fail before any mutation"); (3) **a camada `ui\` nunca passou pelo gate**: `ui\view.py` 13 sobreviventes, `ui\live.py` 16 (mais 2 sítios sem teste) e `ui\panels.py` 74, todos em código antigo (aritmética de layout). **Resolvido no mesmo dia:** testes novos `tests\ui\test_view_exact.py`, `test_live_exact.py` e `test_panels_exact.py` (cada cenário de painel, em vários tamanhos e temas, comparado por hash de família em `tests\ui\panels_golden.json`, 6,8 KB; o primeiro formato tinha 4,6 MB) levaram a camada de 103 para 12 sobreviventes, todos equivalentes. **Três pontos reescritos no código, sem suprimir:** `ui\view.py::_count` (`max(value, 0)`) e `ui\live.py::LiveRenderer.update` (o fatiamento já dá vazio para zero ou negativo; sem o `if new > 0` nem o piso). **Nove suprimidos** em `mutation-suppressions.toml`, com `reason` e aprovação do dono nesta data (`min`/`max` de `ui\panels.py` em `tasks`, `attempt`, `_title` e `rejections` que o corte final ou o `_finish` iguala). Gate sem `--reuse-coverage`: `view.py`, `live.py` e `panels.py` e `core\dependencies.py` ("all mutants killed or suppressed"). **Nenhum sobrevivente vivo no repositório.** Limite das supressões: valem por arquivo, função e mudança, não por linha; quem alterar essas quatro funções relê os `reason`.








## Estado dos incrementos

| Inc. | Estado |
| --- | --- |
| 0, 1, 2 | concluídos |
| 3 | 3a, 3b, 3c e 3d concluídos; 3e suprimido (ordem do dono, 29/10); 3f é do dono (fila 8) |
| 4 | concluído (fila 2) |
| 5 | concluído (filas 1, 4 e 5: gates 6, 9, 10 e 11); falta só o E2E real, do dono |
| 6 | concluído (fila 3); falta só o E2E real, do dono |
| 7 | concluído (filas 7, 9 e 10); promoção de gates dispensada pelo dono (31/10); falta só o E2E real, do dono |

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

**Escopo:** papel de autor de testes; gate vermelho/verde; congelamento de testes; mutação e CRAP; métricas opostas (*pass-through*, profundidade de módulo); segunda CLI com diversidade de autor; adaptador de TypeScript; cache de medições pela chave completa do contrato 5 (3e: suprimido por ordem do dono em 29/10/2026).

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
| Evidência reaproveitada de outro contexto de medição | Gate decide com dado desatualizado | Chave de cache com commit, ferramenta, configuração, toolchain, plataforma e escopo (a chave existe em `core`; o reaproveitamento não foi construído, 3e suprimido em 29/10/2026: cada medição é refeita) |
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
