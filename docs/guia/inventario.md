# Inventário do que a pessoa pode fornecer ou usar na Forja

Este inventário foi extraído do código. Cada item traz nome exato, tipo, padrão, valores aceitos, efeito e `arquivo:linha` (caminhos relativos a `src\forja\`). O que não foi visto no código está marcado como NÃO CONFIRMADO.

## 1. Comandos e argumentos da CLI

Definição: `cli\args.py`, função `parser()` na linha 46, `prog="forja"`. Sem verbo, o comando `forja` pergunta o que fazer (fluxo em `cli\main.py:172-215`).

### 1.1 Verbos e subcomandos

| Comando | Efeito | Fonte |
|---|---|---|
| `forja refatorar` | melhora o código sem mudar o comportamento | `args.py:17-22` |
| `forja corrigir` | corrige um erro descrito pela pessoa | `args.py:17-22` |
| `forja criar` | cria um projeto, num diretório vazio, a partir de uma ideia | `args.py:17-22` |
| `forja investigar` | entende o código a partir de uma pergunta e escreve a documentação | `args.py:17-22` |
| `forja doctor` | verifica ferramentas, CLIs de agente e terminal | `args.py:106`, `main.py:221-232` |
| `forja instalar` | instala as ferramentas externas que faltam | `args.py:107`, `main.py:233-236` |
| `forja revisao [execucao]` | mostra o que de uma execução chegou na branch principal | `args.py:108-127`, `main.py:239-240` |
| `forja agente testar\|lint\|medir [CAMINHO...]` | fachada usada pelo agente; oculta da ajuda | `args.py:128-131`, `cli\facade.py` |

### 1.2 Opções globais

Ficam no parser principal e se repetem em cada verbo com padrão `argparse.SUPPRESS` (`args.py:52-105`).

| Opção | Tipo | Padrão | Efeito |
|---|---|---|---|
| `--escopo CAMINHO` | texto, repetível (append) | nenhum | limita o que a execução pode mudar |
| `--cli NOME` | escolha: `claude-code`, `codex`, `cursor`, `grok` | `claude-code` (`executors\__init__.py:13-19`) | CLI de agente que escreve o código |
| `--cli-testes NOME` | mesma lista | NÃO CONFIRMADO | CLI de agente que escreve os testes |
| `--modelo NOME` | texto | vazio | modelo do agente de código |
| `--modelo-testes NOME` | texto | vazio | modelo do agente de testes |
| `--plano` | flag | desligado | só mostra o plano e sai com código 0 (`main.py:194-197`) |
| `--semgrep-config CAMINHO` | texto | nenhum | regras do Semgrep; referência de registro é recusada |
| `--fatos ARQUIVO` | caminho | nenhum | arquivo de fatos (seção 4.1) |
| `--config ARQUIVO` | caminho | nenhum | roda sem perguntas com um `execucao.toml` (`main.py:177-178`) |

### 1.3 Argumentos de cada verbo

| Argumento | Tipo | Efeito | Fonte |
|---|---|---|---|
| `texto` (posicional, opcional) | texto | a descrição: defeito, pergunta ou ideia | `args.py:87-105` |
| `-f`, `--arquivo` | caminho | lê a descrição de um arquivo UTF-8 | `args.py:87-105` |
| `--criterios ARQUIVO` | caminho | só em `corrigir`; arquivo de critérios (seção 4.2) | `args.py:91-97` |

### 1.4 `forja revisao`

| Argumento | Tipo | Padrão | Efeito |
|---|---|---|---|
| `execucao` (posicional) | id | a mais recente do repositório | qual execução revisar (`review.py:40`) |
| `--principal REF` | texto | `origin/HEAD` | branch principal a ler (`review.py:52`) |
| `--fatos ARQUIVO` | caminho | nenhum | aqui o arquivo carrega os comentários do revisor (`review.py:92`) |

O relatório vai para `FORJA_HOME/revisoes/<id>.md` (`review.py:31,142`). O que `doctor`, `instalar` e `revisao` imprimem linha a linha: NÃO CONFIRMADO.

### 1.5 `forja agente` (fachada)

| Subcomando | Ferramenta chamada | Padrão de CAMINHO |
|---|---|---|
| `testar` | `pytest -q -x -p no:cacheprovider` | NÃO CONFIRMADO |
| `lint` | `ruff check --no-cache` | `.` |
| `medir` | `lizard` | `.` |

Regras (`facade.py`): caminho relativo, existente, dentro do diretório atual, sem `-` inicial, sem `..`, não absoluto; senão sai com 2 e a mensagem "caminho não permitido" ou "caminho não encontrado dentro do projeto". Uso incorreto imprime `uso: forja agente testar|lint|medir [CAMINHO...]` e sai com 2. Limite de 600 s (`TIMEOUT_SECONDS`): sai com 124 e "interrompido: passou de 600 s". Erro de sistema ao abrir a ferramenta: 127. Mostra as últimas 80 linhas (`TAIL_LINES`). O ambiente passado é limitado a PATH, SYSTEMROOT, TEMP, TMP, TMPDIR, PATHEXT, COMSPEC, HOME, USERPROFILE, LANG, LC_ALL, mais `PYTHONDONTWRITEBYTECODE=1`.

### 1.6 Códigos de saída

Definição: `orchestrator\outcome.py:9-16`; regra em `cli\run.py:123-133`.

| Código | Nome | Significado |
|---|---|---|
| 0 | DELIVERED | entregue |
| 1 | FAILED | falhou |
| 2 | INVALID_CONFIG | configuração ou política inválida, repositório ocupado |
| 3 | PAUSED | pausada; rode `forja` de novo para retomar |
| 4 | NOTHING_INTEGRATED | entregue, mas havia tarefas bloqueadas e nenhuma integrada |
| 5 | SOME_BLOCKED | entregue, com algumas tarefas bloqueadas |
| 130 | INTERRUPTED | interrompida pela pessoa |

### 1.7 Mensagens de fechamento

`cli\run.py:136-164`: "Interrompida. Tudo foi salvo."; "Rode `forja` de novo neste repositório para retomar de onde parou."; "N de M tarefa(s) integrada(s); K bloqueada(s)"; "Nenhuma tarefa foi integrada: a branch não tem mudanças."; "Branch da entrega: forja-run/<id> (sua branch não foi alterada; nada foi enviado)."; "Resumo: <dir>/resumo.md"; "Para ver: git log --oneline <branch>".

### 1.8 Execução incompleta

Se houver execução incompleta no repositório, a Forja oferece "retomar de onde parou" ou "descartar e recomeçar" (`main.py:77-88`). Com `--config` ou sem terminal ela se recusa: "Resolva a execução incompleta (rode `forja` sem --config) antes." Descartar não apaga nada e mostra os comandos para limpar as branches (`main.py:138-142`, `resume.py:114-115`). Pergunta "Lembrar de usar sempre <caminho> para <cli>?" grava no perfil (`main.py:91-98`).

Itens da seção 1: 8 comandos, 9 opções globais, 3 argumentos de verbo, 3 argumentos de `revisao`, 3 subcomandos de `agente`, 7 códigos de saída. Total 33.

## 2. `execucao.toml` e `config.toml` do perfil

Modelos pydantic com `extra="forbid"`: chave desconhecida é erro (`cli\settings.py`). TOML inválido gera `SettingsError` "<caminho> is not valid TOML: ..."; erro de validação gera "<caminho>: campo: mensagem" (`settings.py:126`). `save_execucao` grava UTF-8 com LF (`settings.py:177`). A Forja grava uma cópia usada em `runs/<id>/execucao.toml` (`main.py:214`).

### 2.1 Chaves do `execucao.toml` (`settings.py:58-85`)

| Chave | Tipo | Padrão | Valores | Efeito |
|---|---|---|---|---|
| `objetivo` | texto | `"refatorar"` | `refatorar`, `corrigir`, `investigar`, `criar` | o verbo |
| `descricao` | texto | `""` | livre | defeito, pergunta ou ideia |
| `arquivo` | texto | `""` | caminho | arquivo com a descrição |
| `criterios` | texto | `""` | caminho | arquivo de critérios |
| `cli` | texto | `""` | nome de CLI | CLI do agente de código |
| `executavel` | texto | `""` | caminho | executável dessa CLI |
| `cli_testes` | texto | `""` | nome de CLI | CLI do agente de testes |
| `executavel_testes` | texto | `""` | caminho | executável dessa CLI |
| `modelo` | texto | `""` | livre | modelo do agente de código |
| `modelo_testes` | texto | `""` | livre | modelo do agente de testes |
| `escopo` | lista de texto | vazia | caminhos | limita o que pode mudar |
| `tokens` | inteiro | 2000000 (`settings.py:20`) | `>= 1` | orçamento de tokens |
| `agente_roda_testes` | booleano | `true` | | o agente pode rodar os testes pela fachada |
| `tarefas` | inteiro | 5 | `>= 1` | número de tarefas |
| `paralelismo` | inteiro | 1 | `>= 1` | tarefas em paralelo |
| `base` | texto | `""` | NÃO CONFIRMADO | base do projeto (deslocamento das camadas) |
| `semgrep_config` | texto | `""` | caminho local | regras do Semgrep |
| `linguagem` | texto | `""` | NÃO CONFIRMADO | linguagem, obrigatória em `criar` (`prepare.py:169`) |
| `nome` | texto | `""` | palavras minúsculas ligadas por hífen, até 40 caracteres (`prepare.py:186`) | nome do projeto em `criar` |
| `fatos` | texto | `""` | caminho | arquivo de fatos |
| `instalar_ferramentas` | booleano | `false` | | sem terminal, permite instalar ferramentas (`main.py:158-163`) |
| `clis` | tabela de `ModeloCli` | vazia | | define CLIs além das conhecidas (2.3) |
| `interface` | tabela `Interface` | ver 2.2 | | aparência da tela |

Mensagens que citam `objetivo`, `linguagem` e `nome`: `prepare.py:79,169,186`. Quais chaves são obrigatórias sem terminal: NÃO CONFIRMADO.

### 2.2 Tabela `[interface]` (`settings.py:28-34`)

| Chave | Tipo | Padrão | Valores | Efeito |
|---|---|---|---|---|
| `modo` | texto | `"auto"` | `auto`, `completa`, `linha`, `texto` | força o nível de tela |
| `tema` | texto | `""` | `escuro`, `darcula`, `claro`, `contraste`, `neon`, `dos` | vazio segue o fundo do terminal |
| `ascii` | booleano | `false` | | usa glifos ASCII |
| `redimensionar` | booleano | `true` | | tenta ampliar a janela (só xterm, mintty, iTerm) |

### 2.3 Tabela `[clis.<nome>]` (`ModeloCli`, `settings.py:37-55`)

| Chave | Tipo | Padrão | Efeito |
|---|---|---|---|
| `comando` | lista de texto, mínimo 1 | obrigatória | argv; marcadores `{executable}`, `{package}`, `{cwd}`, `{role}` |
| `pacote_por_stdin` | booleano | `false` | envia o pacote por stdin |
| `executaveis` | lista de texto | vazia | nomes de executável; vazio usa o nome da CLI |
| `versao` | lista de texto | `["--version"]` | argv que prova a versão |
| `ambiente` | lista de texto | vazia | variáveis de ambiente que a CLI pode ver |

### 2.4 Perfil `config.toml` (`Perfil`, `settings.py:88-96`)

Local: pasta do perfil (seção 5), arquivo `config.toml` (`settings.py:135,183`). Arquivo ausente vale como perfil vazio.

| Chave | Tipo | Padrão | Efeito |
|---|---|---|---|
| `cli` | texto | `""` | CLI preferida |
| `executaveis` | tabela nome para caminho | vazia | executável de cada CLI |
| `clis` | tabela de `ModeloCli` | vazia | mesmo formato de 2.3 |
| `interface` | tabela `Interface` | ver 2.2 | usada quando não há `execucao.toml` (`main.py:62`) |

Ordem de resolução do executável: explícito, `FORJA_EXECUTOR_<NOME>`, `executaveis` do perfil, descoberta (`core\adapters\executor.py:226,247`).

Itens da seção 2: 23 chaves de `execucao.toml`, 4 de `[interface]`, 5 de `[clis.<nome>]`, 4 do perfil. Total 36.

## 3. `forja.toml` (política do repositório)

Só o `forja.toml` na raiz do repositório é lido pela CLI (`cli\session.py:179`, `load_policy(default_registry(), repo=repo / "forja.toml")`). A função `load_policy` também aceita camadas de usuário e de execução, mas a CLI não as usa. Arquivo ausente significa padrões. Erros geram "O forja.toml deste repositório tem erros" (`prepare.py:585`). A política entra num resumo `sha256:`; mudar entre pausa e retomada gera `PolicyChanged` (`session.py:328-335`). Mudanças em relação aos padrões são listadas em `prepare.py:361-376`.

Seções aceitas (`core\policy\config.py:253-264`): `checks`, `sensitive`, `branches`, `adapters`, `redaction`, `tests`, `licenses`, `voice`, `architecture`, `differential`. Qualquer outra gera "unknown section". Entre camadas, valores sobrepõem valor a valor (`config.py:700-736`) e listas se somam.

### 3.1 `[checks.<id>]` (`config.py:39`)

| Chave | Tipo | Valores | Efeito |
|---|---|---|---|
| `mode` | texto | `blocking`, `observation` (`gates\models.py:12-14`) | reprova ou só observa |
| `on_inconclusive` | texto | `block`, `premise` (`models.py:17-19`) | o que fazer quando não dá para medir; verificação bloqueante exige um dos dois (`config.py:721`) |
| `promotion` | tabela `{ date, reason }` | exatamente essas duas chaves | obrigatória ao promover de observação a bloqueante; inválida nos outros casos (`config.py:689-697`) |
| `thresholds.<linguagem>.<nome>` | número finito | linguagem em java, go, python, csharp, javascript, typescript (`registry.py:8`); nome tem que existir na verificação | limiar por linguagem |
| `commands.<nome>` | lista de texto não vazia | sem string de shell | substitui o comando |
| `limits.<nome>` | número finito, zero ou mais | | limite |

`voice` e `comments` nunca aceitam `mode = "blocking"` (`config.py:42`).

### 3.2 Verificações (`checks\specs.py:14-86`)

34 verificações em 14 portões. Colunas: id, portão, modo padrão, `on_inconclusive` padrão, chaves aceitas.

| id | Portão | Modo | on_inconclusive | Chaves |
|---|---|---|---|---|
| scope | 1 | blocking | block | limits `max_files`, `max_lines` |
| freeze | 1 | blocking | block | |
| secrets | 2 | blocking | block | |
| dependency_install | 2 | blocking | block | |
| format | 3 | blocking | block | commands `format` |
| lint | 3 | blocking | block | commands `lint` |
| types | 3 | observation | premise | commands `types` |
| build | 4 | blocking | block | commands `build` |
| tests | 5 | blocking | block | commands `test` |
| red_green | 5 | blocking | block | commands `test` |
| e2e | 6 | observation | block | |
| test_data | 6 | observation | premise | |
| properties | 6 | observation | premise | |
| mutation | 7 | observation | premise | thresholds `min_score`; limits `workers` |
| complexity | 8 | blocking | premise | thresholds `max_ccn` |
| crap | 8 | observation | premise | thresholds `max_crap` |
| pass_through | 8 | observation | premise | |
| module_depth | 8 | observation | premise | thresholds `max_interface_ratio`, `min_statements` |
| duplication | 8 | observation | premise | limits `min_tokens`, `min_lines` |
| dependency_cycles | 9 | observation | block | |
| layer_rules | 9 | observation | block | |
| package_metrics | 9 | observation | premise | thresholds `max_distance`, `min_types` |
| sast | 10 | observation | block | |
| dependency_audit | 10 | observation | block | |
| new_dependency | 10 | observation | premise | thresholds `min_age_days`, `min_downloads` |
| differential | 11 | observation | premise | thresholds `max_time_ratio`, `max_memory_ratio`, `runs` |
| voice | 12 | observation | premise | limits `max_dashes` |
| comments | 12 | observation | premise | |
| citations | 13 | observation | block | |
| traceability | 13 | observation | block | |
| change_record | 14 | observation | block | |
| readme | 14 | observation | premise | |
| doc_drift | 14 | observation | premise | |
| adr | 14 | observation | premise | |

Valores padrão dos limiares e limites:

| Verificação | Chave | Padrão | Fonte |
|---|---|---|---|
| complexity | `max_ccn` | 15 | `complexity.py:23` |
| crap | `max_crap` | 30.0 | `crap.py:22` |
| mutation | `min_score` | 0.80; 0.70 para python e go | `mutation.py:50-52` |
| mutation | `workers` | inteiro positivo; padrão NÃO CONFIRMADO | |
| module_depth | `max_interface_ratio` | 1.0 | `module_depth.py:20` |
| module_depth | `min_statements` | 10 | `module_depth.py:21` |
| package_metrics | `max_distance` | 0.8 | `package_metrics.py:17` |
| package_metrics | `min_types` | 3 | `package_metrics.py:18` |
| new_dependency | `min_age_days` | 30 | `new_dependency.py:30` |
| new_dependency | `min_downloads` | 100 | `new_dependency.py:31` |
| differential | `max_time_ratio` | 1.25 | `differential.py:35` |
| differential | `max_memory_ratio` | 1.25 | `differential.py:36` |
| differential | `runs` | 3 | `differential.py:37` |
| duplication | `min_tokens` | 50 | `duplication.py:33` |
| duplication | `min_lines` | 5 | `duplication.py:34` |
| voice | `max_dashes` | 3 | |
| scope | `max_files`, `max_lines` | vale o mais estrito entre tarefa e política; zero significa sem limite (`scope.py:65-73`) | |

### 3.3 Outras seções

| Seção e chave | Tipo | Regra |
|---|---|---|
| `[adapters.<linguagem>.commands]` | tabela operação para lista de texto | operações: `format`, `lint`, `lint_fix`, `types`, `build`, `test`, `coverage`, `mutation`, `e2e` (`config.py:45`); argv não vazio; sem padrão para `e2e` (`session.py:168-173`, `e2e_plan.py`) |
| `[sensitive] paths` | lista de padrões | caminhos sensíveis |
| `[branches] protected` | lista de nomes | sem espaço e sem `-` inicial |
| `[licenses] forbidden` | lista de ids SPDX | sem espaço; não há lista padrão |
| `[tests] root` | texto | diretório dentro do repositório, em formato POSIX |
| `[voice] markers_extra` | lista de regex | não pode casar vazio; ids viram `repository-N` |
| `[voice] markers_off` | lista de ids | formato `[a-z][a-z0-9-]*`; ids da Forja: greeting, self-reference, inflated, announcement, offer, emoji (`voice_markers.py`) |
| `[redaction]` tabela de padrões | nome para regex | padrões de redação |
| `[redaction] allow` | lista de texto | cada item até 500 caracteres |
| `[redaction] allow_patterns` | lista de regex | regex válidas |
| `[redaction] pii` | lista | subconjunto de `cpf`, `cnpj`, `email`, `phone`, `card`; a última camada substitui |
| `[redaction] entropy_threshold` | número | 0 a 8; padrão 2.5 (`redaction\settings.py:60`) |
| `[architecture] layers` | lista de `{name, paths}` | nome não vazio e único; `paths` lista não vazia de diretórios relativos POSIX; ordem de cima para baixo; camada depende de si e das de baixo (`layer_rules.py`); só arestas novas da tentativa reprovam; diretório fora de camada é livre; camadas são caminhos do repositório |
| `[differential] cases` | lista de casos | ver 3.4 |

### 3.4 Casos de `[differential]` (`core\policy\differential.py`)

| Chave | Tipo | Regra |
|---|---|---|
| `name` | texto | `[a-z0-9][a-z0-9_-]*`, único |
| `command` | lista de texto | o programa não pode ser shell: sh, bash, zsh, dash, ksh, fish, cmd, powershell, pwsh (sem `.exe`) |
| `cwd` | texto | caminho relativo POSIX |
| `stdin` | texto | caminho relativo POSIX; copiado da base como `<caso>.stdin` (`differential_inputs.py`); `MissingInput` se não for arquivo comum do repositório |
| `outputs` | lista não vazia de `{kind, path, rule, ignore}` | padrão: `stdout` bytes mais `exit_code` bytes |
| `outputs.kind` | texto | `stdout`, `exit_code`, `file`; só `file` tem e exige `path` |
| `outputs.rule` | texto | `bytes` (padrão), `json`, `ignore`; `exit_code` só aceita `bytes` |
| `outputs.ignore` | lista de regex | obrigatória e não vazia com `rule = "ignore"`, proibida nos outros; regex não podem casar vazio |
| `outputs` duplicado | | par (kind, path) repetido é recusado |

### 3.5 Detalhes de verificações lidos no código

README (`readme.py:22-29`): exige as seções what, build, test, run, configure, dependencies, reconhecidas por regex de título; aceita `README.md` e `README.rst`. Voz: `MAX_DASHES=3`.

Itens da seção 3: 34 verificações, 6 chaves de `[checks.<id>]`, 9 operações de adapter, 12 chaves das demais seções, 4+ casos de differential (9 linhas), 17 limiares e limites com padrão. Total aproximado 110 linhas de item.

## 4. Arquivos de entrada que a pessoa escreve

### 4.1 Arquivo de fatos (`orchestrator\facts.py`)

Passado por `--fatos` ou `fatos` no `execucao.toml`.

| Regra | Valor |
|---|---|
| formato da linha | `id \| autor \| data \| texto` (4 campos), ou 5 com `confirma:<id>` ou `corrige:<id>` |
| linhas ignoradas | em branco e iniciadas por `#` |
| `id` | `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`, único |
| `data` | ISO `AAAA-MM-DD` |
| id de premissa | `^p[0-9a-f]{8}$` (aparece no resumo) |
| erros | citam a linha |

Em `revisao`, o mesmo formato carrega os comentários do revisor.

### 4.2 Arquivo de critérios (`criterios.json`)

Fonte, nesta ordem: `--criterios` ou `criterios` do `execucao.toml`; senão `criterios.json` ao lado do arquivo `-f`; senão um agente escreve (`prepare.py:52,105-121`).

| Campo | Tipo | Regra | Fonte |
|---|---|---|---|
| `criteria` | lista | pelo menos 1 item; ids únicos | `core\artifacts\schemas.py:71` |
| `id` | inteiro | `>= 1` | `llm_output.py:148` |
| `text` | texto | não vazio | idem |
| `level` | texto | `unit`, `integration`, `e2e` | idem |
| `origin` | lista de texto | não vazia; texto único vira lista de um; ids dos elementos da entrada, como E1, E2 | idem |

### 4.3 Descrição por arquivo

`-f/--arquivo` lê UTF-8: em `corrigir` o defeito, em `investigar` a pergunta, em `criar` a ideia. O erro cita o que se lia.

### 4.4 Regras do Semgrep (`cli\semgrep_rules.py`)

Origem: `--semgrep-config` ou `semgrep_config`; senão `.semgrep.yml` ou pasta `.semgrep/` no commit base. Referência de registro é recusada (`auto`, `p/`, `r/`, `s/`, `semgrep.dev/`, `://`). Caminho local tem de existir. Nomes com barra invertida, dois pontos, NUL, `..` ou `.` são recusados. A execução lê uma cópia em `runs/<id>/semgrep-rules` com o ponto inicial removido (`session.py:412`). Sem regras o SAST não roda e aparece um aviso.

### 4.5 Comando de e2e

Vem de `[adapters.<linguagem>.commands] e2e` no `forja.toml`. Roda com rede desligada na medida do possível: variáveis de proxy (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, maiúsculas e minúsculas), `NO_PROXY=localhost,127.0.0.1,::1`, `npm_config_offline=true`, `PIP_NO_INDEX=1`, `GOPROXY=off`, `NODE_USE_ENV_PROXY=1` e `JAVA_TOOL_OPTIONS` com propriedades de proxy (`e2e_plan.py:22-51`).

### 4.6 Camadas, casos diferenciais, licenças proibidas

Não há arquivos separados: são `[architecture]`, `[differential]` e `[licenses]` do `forja.toml` (seção 3).

### 4.7 Arquivos do projeto lidos pelas verificações

Auditoria de dependências lê (`dependency_audit.py:35-39`): requirements.txt, Pipfile.lock, poetry.lock, pdm.lock, uv.lock, pylock.toml, package-lock.json, pnpm-lock.yaml, yarn.lock, bun.lock, packages.lock.json, packages.config, deps.json. Lista completa: NÃO CONFIRMADO. `package.json` fica com `new_dependency`.

Itens da seção 4: 6 regras de fatos, 5 campos de critérios, 1 descrição, 1 regra Semgrep (várias origens), 1 comando e2e, 13 arquivos de dependências. Total 27.

## 5. Variáveis de ambiente

| Variável | Efeito | Fonte |
|---|---|---|
| `FORJA_HOME` | raiz dos dados da Forja | `core\paths.py:21` |
| `FORJA_CONFIG_HOME` | pasta do perfil | `settings.py:102` |
| `FORJA_AGENT_PYTHON` | python que a fachada `testar` usa; definido pela Forja com o python do repositório | `facade.py:17,62`, `session.py:463`, `claude_code.py:68` |
| `FORJA_EXECUTOR_<NOME>` | executável do adapter; NOME em maiúsculas, não alfanumérico vira `_` | `core\adapters\executor.py:226,247` |
| `APPDATA` | perfil no Windows: `%APPDATA%\forja` | `settings.py:99-107` |
| `XDG_CONFIG_HOME` | perfil fora do Windows: `$XDG_CONFIG_HOME/forja`, senão `~/.config/forja` | `settings.py:99-107` |
| `LOCALAPPDATA` | dados no Windows: `%LOCALAPPDATA%\forja` | `core\paths.py` |
| `PATH` | descoberta de executáveis | NÃO CONFIRMADO (uso geral) |
| `WT_SESSION`, `TERM_PROGRAM` (vscode, mintty, iTerm.app), `TMUX`, `STY`, `MSYSTEM` | detecção do terminal | `ui\terminal.py` |
| `TERM` (xterm*, dumb, *256color) | capacidade do terminal | `ui\terminal.py` |
| `COLORTERM` (`truecolor`, `24bit`) | cor de 24 bits | `ui\terminal.py` |
| `NO_COLOR` | desliga cor | `ui\terminal.py` |
| `COLORFGBG` | fundo claro ou escuro | `ui\terminal.py` |
| `NO_MOTION`, `REDUCE_MOTION` | reduz animação | `ui\terminal.py` |

`GIT_DIR` é definido pela Forja como `.forja-no-git-repository` na cópia do agente (`core\isolation\environment.py:66`); não é configuração da pessoa. Lista completa das variáveis lidas por `doctor` e pelos adapters de executor: NÃO CONFIRMADO.

Itens da seção 5: 17 variáveis nomeadas (4 da Forja, 3 de pasta, 1 PATH, 9 de terminal).

## 6. Arquivos e pastas que a Forja cria

### 6.1 `FORJA_HOME` (`core\paths.py`)

Windows: `%LOCALAPPDATA%\forja` (reserva `~/AppData/Local/forja`). Outros: `~/.local/share/forja`.

| Caminho | Conteúdo | Fonte |
|---|---|---|
| `runs/<id>/events.jsonl` | registro de eventos | `session.py:324`, `review.py:112` |
| `runs/<id>/logs/git` | logs do git | `session.py:341` |
| `runs/<id>/execucao.toml` | cópia das opções da execução | `main.py:214` |
| `runs/<id>/resumo.md` | resumo final | `phases.py:42` |
| `runs/<id>/semgrep-rules` | cópia das regras | `session.py:412` |
| `locks/<repo_id>/` | trava do repositório | `session.py:344`, `paths.py:30` |
| `revisoes/<id>.md` | relatório de `revisao` | `review.py:31,142` |
| `tools/` | ferramentas instaladas; marcador `.forja-installed` | `toolchain\install.py:62,30` |

### 6.2 Pasta do perfil

`config.toml` e `provas.json` (cache das provas do `doctor`, `prepare.py:302-303`).

### 6.3 No repositório (git)

| Item | Detalhe | Fonte |
|---|---|---|
| branch da entrega | `forja-run/<id>`, em worktree próprio | resumo de `run.py` |
| branches de tarefa | `forja/<execucao>/<tarefa>` | NÃO CONFIRMADO na fonte |
| worktrees descartáveis | um por tentativa | NÃO CONFIRMADO na fonte |
| autor dos commits | `Forja (<cli>)`, e-mail `forja@localhost` | `workspace_git.py:49-50,112` |
| push | a Forja nunca envia; sua branch não é alterada | `run.py:136-164` |
| `docs/mudancas/<tarefa>.md` e `docs/mudancas/<tarefa>-diario.md` | registro de mudança | `change_record.py:45,77,82` |

### 6.4 Cópia de trabalho do agente (sem `.git`)

Pasta `.forja-agent/` (`executor.py:16`): `diary.md` (diário), `package.md` (pacote, `agent_runner.py:76`), `saida.json` (saída, `agent_runner.py:88`). O agente não pode mudar seus arquivos de permissão nem o diário (`agent_runner.py:763-770`).

### 6.5 Arquivos de medição

`base.json` e `base-metrics.json` (`measurer.py:121-122`); logs em `<workdir>/tools/<alvo>` (`measurer.py:217`); `jscpd-report.json` e `jscpd.json` (duplicação); `gitleaks.json` e `added.txt` (segredos); relatórios `<nome>.json` do SAST e da auditoria. Caminhos exatos de cada um: NÃO CONFIRMADO.

### 6.6 `forja criar`

Escreve os arquivos do modelo, cria `.git` se faltar, comita e roda um comando de preparação (`cli\scaffold.py`). Recusa diretório não vazio ("precisa estar vazio"). Prazo do comando (`SETUP_SECONDS`): NÃO CONFIRMADO.

### 6.7 Ferramentas externas instaladas (`toolchain\manifest.toml`)

gitleaks 8.30.1, osv-scanner 2.7.0, jscpd 5.4.2, semgrep 1.183.0 (wheel), mypy 2.4.1 (wheel), go 1.27.3, golangci-lint 2.15.0, node 26.13.0, dotnet-sdk 10.0.403 (executável `dotnet`), jdk, maven, gradle (versões dos três últimos: NÃO CONFIRMADO). Alvos vistos: windows-x64 e linux-x64. No Windows a execução pede ao sistema que não suspenda (`cli\awake.py`, `SetThreadExecutionState`); em outras plataformas: NÃO CONFIRMADO.

Itens da seção 6: 8 caminhos em `FORJA_HOME`, 2 no perfil, 6 no git, 3 em `.forja-agent`, 6 de medição, 12 ferramentas. Total 37.

## 7. Linguagens suportadas e requisitos

A política aceita os nomes java, go, python, csharp, javascript, typescript (`registry.py:8`). Há adapter e detecção para cinco: python, go, typescript, csharp, java. Não foi vista pasta de adapter nem detecção para javascript; `criar` não gera javascript (`scaffold.py:42-52`). Estado de javascript: NÃO CONFIRMADO.

### 7.1 Detecção (`cli\detect.py:96-107`)

| Linguagem | Arquivo que a identifica |
|---|---|
| python | `pyproject.toml` |
| go | `go.mod` |
| java | `pom.xml`, `build.gradle` ou `build.gradle.kts`; Maven quando há `pom.xml`; Gradle sem `gradlew` ou `gradlew.bat` é sinalizado |
| csharp | `*.sln` ou `*.csproj` (o adapter também lê `*.slnx`) |
| typescript | `package.json` com `tsconfig.json` |

Sem detecção, a mensagem (`prepare.py:238-239`) lista: pyproject.toml, go.mod, package.json com tsconfig.json, .sln ou .csproj, pom.xml ou build.gradle[.kts].

### 7.2 Python (`languages\python\adapter.py`)

| Operação | Comando |
|---|---|
| format | `ruff format [--check] --no-cache --force-exclude` |
| lint | `ruff check --ignore-noqa --output-format=concise --no-cache --force-exclude` |
| lint_fix | `ruff check --fix --exit-zero` |
| types | mypy com `--config-file=` (a configuração do repositório não é lida), `--follow-imports=silent`, `--output json`, ignorando import-not-found e import-untyped |
| build | `python -m compileall -q` |
| test | `python -m pytest -p no:cacheprovider -q -rA --color=no` (acrescenta `--hypothesis-seed` se hypothesis estiver declarado) |
| coverage | driver de coverage, saída `target/coverage/python/coverage.json` |

Raiz de testes `tests`; arquivos de configuração `pyproject.toml`, `ruff.toml`, `.ruff.toml`, `setup.cfg`, `pytest.ini`, `tox.ini`; ecossistema PyPI; fontes `.py` e `.pyi`; teste é o que está em `tests/` ou `test/`, ou `test_*`, `*_test.py`, `conftest.py`.

### 7.3 Demais linguagens

| Linguagem | Manifesto | Ferramentas | Cobertura | Ecossistema |
|---|---|---|---|---|
| go | `go.mod` | gofmt, golangci-lint, go | `.forja-cover.out` | Go |
| typescript | `package.json` e `tsconfig.json` | vitest ou jest via node | `<pasta de cobertura>/coverage-final.json` (nome da pasta: NÃO CONFIRMADO) | npm |
| csharp | `*.sln`, `*.slnx`, `*.csproj` | dotnet, `dotnet format` | `<pasta de cobertura>/*/coverage.cobertura.xml` | NuGet |
| java | `pom.xml` ou `build.gradle[.kts]` | spotless, checkstyle, pmd, spotbugs, jacoco | `target/site/jacoco/jacoco.xml` (Maven) | Maven |

Argumentos exatos dos comandos de go, typescript, csharp e java: NÃO CONFIRMADO.

### 7.4 `forja doctor` (`cli\doctor.py`)

Verifica por linguagem: mypy (python); go e golangci-lint; node; dotnet; java e mvn ou gradle; também gitleaks, jscpd, semgrep, a prova da CLI de agente e das demais CLIs, e uma nota do terminal. Linhas exatas: NÃO CONFIRMADO.

### 7.5 CLIs de agente (`executors\__init__.py:13-19`)

`claude-code` (padrão), `codex`, `cursor`, `grok`. O adapter do Gemini existe em `executors\gemini.py` mas não está registrado (suspenso). Opções detalhadas de `codex`, `cursor` e `grok`: NÃO CONFIRMADO.

Itens da seção 7: 6 nomes de linguagem na política, 5 com adapter, 7 operações Python, 4 linguagens na tabela 7.3, 4 CLIs. Total 26.

## 8. Teclas, temas e modos da interface

### 8.1 Níveis de tela (`ui\terminal.py`)

| Nível | Nome | Regra |
|---|---|---|
| completa | `Tier.FULL` | tela cheia; mínimo 60 colunas por 16 linhas, recomendado 120 por 36 |
| linha | `Tier.LIVE` | linha ao vivo |
| texto | `Tier.TEXT` | texto simples, para pipe e CI |

`choose_tier`: saída sem terminal dá texto; janela abaixo de 60x16 cai para linha com a mensagem "a janela está pequena (CxL); a tela completa pede ao menos 60x16"; nível forçado diferente de texto em saída sem terminal dá texto com "a saída não é um terminal". O redimensionamento só ocorre em xterm, mintty e iTerm, só para ampliar, nunca em multiplexador ou terminal embutido. Detalhes da linha ao vivo (`ui\live.py`) e do texto (`ui\plain.py`): NÃO CONFIRMADO.

### 8.2 Temas (`ui\theme.py:153-248`)

| Chave | Título | Fundo | Notas |
|---|---|---|---|
| `escuro` | Forja Escuro | escuro | padrão com fundo escuro ou desconhecido |
| `darcula` | Forja Darcula | escuro | |
| `claro` | Forja Claro | claro | padrão com fundo claro |
| `contraste` | Alto contraste | escuro | borda simples |
| `neon` | Forja Neon | escuro | títulos espaçados, borda por assunto |
| `dos` | Forja DOS | escuro | borda dupla, títulos de aba, sombra |

A tecla `t` percorre na ordem escuro, darcula, claro, contraste, neon, dos. Nome desconhecido gera `KeyError` "unknown theme ...; the themes are ..."; a comparação ignora maiúsculas. `ascii = true` troca por glifos ASCII.

### 8.3 Teclas durante a execução

| Tecla | Efeito | Fonte |
|---|---|---|
| `q` ou `Q` | parar; a primeira pergunta se salva, a segunda sai de imediato | `keys.py:16`, `run.py:112-120` |
| `ctrl+k` (`\x0b`) | parar | `keys.py:16` |
| `ctrl+c` | parar | `keys.py:16` |
| `t` ou `T` | muda o tema | `keys.py:16` |

### 8.4 Teclas da tela completa (`ui\full.py:137-147`)

| Tecla | Efeito |
|---|---|
| `ctrl+k`, `ctrl+c` | parar (prioridade) |
| `ctrl+q` | nada |
| `t` | tema |
| `?` | ajuda |
| `d` | detalhes da tarefa atual; de novo fecha |
| `l` | log da atividade; de novo fecha |
| `q` | sair ou parar |
| `escape` | sai de uma sobreposição |
| `up`, `down`, `pageup`, `pagedown`, `end` | rolagem nos painéis (página de 8 linhas) |

Painéis: head, band, body (tarefas, tentativa), rej ("Rejeições"), final ("Fim da execução"), help, details ("Detalhes da tarefa"), log ("Log da atividade"), foot. Classes de tela: narrow, compact, stopping, finished. Texto de ajuda em `ui\panels.py:389-391`. `REFRESH_SECONDS=0.25`.

### 8.5 Tela de instalação (`ui\install_full.py:50-54`)

`ctrl+c` cancela, `ctrl+q` nada, `t` tema, `q` sai.

### 8.6 Barra de portões

A interface mostra 12 portões (`ui\view.py`, `ui\live.py`; por exemplo e2e é o portão 6), enquanto a política tem 14. Mapeamento completo: NÃO CONFIRMADO.

Itens da seção 8: 3 níveis, 6 temas, 4 teclas de execução, 9 teclas da tela completa, 4 teclas da instalação. Total 26.

## Lacunas

1. `--cli-testes`: padrão e regra de herança da `--cli` NÃO CONFIRMADO.
2. `execucao.toml`: valores aceitos de `base` e `linguagem` (além de `criar` exigir linguagem), e quais chaves são obrigatórias sem terminal em `--config`, não foram rastreados.
3. `orchestrator\config.py`, `budget.py`, `planner.py`, `diary.py`, `summary.py` não foram lidos; o padrão de tentativas por tarefa, `files_per_task` e `lines_per_task` ficam NÃO CONFIRMADO.
4. javascript aparece nos nomes aceitos pela política, mas não há detecção nem adapter visto.
5. Comandos exatos de go, typescript, csharp e java, nome da pasta de cobertura de typescript e csharp.
6. Saída linha a linha de `doctor`, `instalar` e `revisao`; `SETUP_SECONDS` de `criar`; versões de jdk, maven e gradle; lista completa dos arquivos lidos pela auditoria de dependências.
7. Opções dos adapters `codex`, `cursor` e `grok` e o uso de `modelo` por cada um (só `claude_code.py` foi lido).
8. Variáveis de ambiente lidas por `doctor` e pelos adapters de executor: apenas buscadas, não lidas.
9. `ui\live.py`, `ui\plain.py`, `ui\view.py`: comportamento e mapeamento de portões não lidos.
10. Mensagens de erro de `config.py` (linhas 41 e 296) citam `docs/voz.md`; o caminho precisa de correção (passo 8 do plano). `FORJA_VERSION = "0.0.0"` está em `session.py:102`.
11. Comportamento de `awake.py` fora do Windows.
