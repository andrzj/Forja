# Modo CI

A Forja roda sem perguntas quando recebe `--config` ou quando não há terminal interativo. Este documento diz quando isso acontece, o que a Forja recusa, como escrever o `execucao.toml` para CI e como a Forja evita que o computador suspenda durante a execução.

## Quando a Forja não pergunta

O modo sem perguntas liga em dois casos:

- `forja --config <arquivo>`: a Forja lê o `execucao.toml` indicado e não pergunta nada, mesmo num terminal interativo. Assim, a execução de CI e a mesma execução digitada à mão dão o mesmo resultado.
- Sem terminal interativo (entrada ou saída redirecionada), mesmo sem `--config`.

Nos dois casos a Forja usa um console que repassa o que tem a dizer e responde a cada pergunta com o valor padrão (`cli\console.py::Unattended`). Também não há a confirmação final "Confirma e começa?": a execução começa sem ela.

O valor padrão só serve quando não muda o resultado. Quando a resposta falta e não há padrão seguro, a Forja recusa a execução e diz onde está a resposta:

| Falta ou há ambiguidade | Mensagem da Forja (resumida) | O que resolve |
| --- | --- | --- |
| Objetivo | "Diga o que fazer: `objetivo` no execucao.toml (...) ou o verbo na linha de comando." | `objetivo` no `execucao.toml` (`refatorar`, `corrigir`, `investigar` ou `criar`), ou o verbo na linha de comando |
| Várias instalações da mesma CLI | "Encontrei N instalações de X e não há quem escolha: dê o caminho em `executavel` no execucao.toml", seguida da lista de caminhos | `executavel` com o caminho desejado. Para o autor de testes, `executavel_testes` |
| CLI não encontrada | "Não encontrei `X` instalado..." | Instalar a CLI e entrar na conta. `forja doctor` mostra o que falta. Ou dar o caminho em `executavel` |
| Linguagem de `criar` | "Diga a linguagem do projeto: `linguagem` no execucao.toml (...)." | `linguagem` no `execucao.toml` |
| Ideia, descrição ou pergunta vazias | "Conte a ideia...", "Descreva o erro...", "Faça a pergunta..." | `descricao`, ou `arquivo` apontando um arquivo com o texto |
| Nome do projeto em `criar` | Sem `nome`, a Forja usa o nome do diretório. Se ele não serve como nome de projeto, a Forja recusa e pede `nome`. | `nome` no `execucao.toml` |
| Execução incompleta neste repositório | "Resolva a execução incompleta (rode `forja` sem --config) antes." | Rodar `forja` num terminal e escolher retomar ou descartar |

Uma CLI conhecida com instalação única não gera pergunta nem recusa: a Forja usa essa instalação.

## execucao.toml completo para CI

O `execucao.toml` guarda as respostas da preparação. Só aceita as chaves da seção `Execucao` do código; chave desconhecida recusa o arquivo. Chave ausente vale o padrão da tabela de chaves, abaixo.

Exemplo completo de uma refatoração em CI. Caminho do Windows vai entre aspas simples (string literal do TOML), senão a barra invertida vira escape:

```toml
# execucao.toml de CI: refatoração de um pacote, sem perguntas
objetivo = "refatorar"
cli = "claude-code"
executavel = "/opt/ferramentas/claude"   # no Windows: 'C:\Ferramentas\claude\claude.exe'
modelo = ""                              # vazio: o modelo configurado na própria CLI
escopo = ["src/meuapp"]
tokens = 2000000
agente_roda_testes = true
tarefas = 5
paralelismo = 1
semgrep_config = ""                      # vazio: nenhuma regra do Semgrep
fatos = ""
clis = {}

[interface]
modo = "texto"
ascii = true
```

Chaves e padrões, conforme `Execucao` em `cli\settings.py`:

| Chave | Padrão | Para quê |
| --- | --- | --- |
| `objetivo` | `"refatorar"` | `refatorar`, `corrigir`, `investigar` ou `criar` |
| `descricao` | `""` | Erro (`corrigir`), pergunta (`investigar`) ou ideia (`criar`). Em `refatorar` é ignorada: a medida escolhe a função, e só os `fatos` conduzem o agente |
| `arquivo` | `""` | Arquivo com a descrição, no lugar de `descricao` |
| `criterios` | `""` | Arquivo de critérios (`corrigir`) |
| `cli` | `""` | CLI do implementador. Vazio: `claude-code` |
| `executavel` | `""` | Caminho do executável da CLI do implementador |
| `cli_testes` | `""` | CLI do autor de testes (`corrigir` e `criar`). Vazio: a do implementador |
| `executavel_testes` | `""` | Caminho do executável do autor de testes |
| `modelo` | `""` | Modelo do implementador. Vazio: o da própria CLI |
| `modelo_testes` | `""` | Modelo do autor de testes. Vazio: o do implementador |
| `escopo` | `[]` | Caminhos do repositório que a execução pode alterar |
| `tokens` | `2000000` | Orçamento de tokens da execução (mínimo 1) |
| `agente_roda_testes` | `true` | Se o agente pode rodar os testes na própria cópia |
| `tarefas` | `5` | Quantas das piores funções uma execução trata (mínimo 1) |
| `paralelismo` | `1` | Tarefas de escopo disjunto que rodam juntas (ver [paralelismo.md](paralelismo.md)) |
| `semgrep_config` | `""` | Arquivo ou diretório com as regras do Semgrep |
| `linguagem` | `""` | Linguagem do projeto novo (`criar`) |
| `nome` | `""` | Nome do projeto novo (`criar`) |
| `fatos` | `""` | Arquivo de fatos do dono |
| `clis` | `{}` | Modelos de CLI descritos por comando (`[clis.<nome>]`, ver [clis-por-papel-e-adaptador-generico.md](clis-por-papel-e-adaptador-generico.md)) |
| `[interface]` `modo` | `"auto"` | `auto`, `completa`, `linha` ou `texto`. Para CI, `texto` |
| `[interface]` `tema`, `ascii`, `redimensionar` | `""`, `false`, `true` | Aparência da tela |

Para `corrigir`, acrescente `descricao` (ou `arquivo`) e, se o autor de testes for outra CLI, `cli_testes` com `executavel_testes`. Para `criar`, `linguagem` é obrigatória sem terminal.

## Arquivo em que se confia

`--config` lê o arquivo e executa o que ele manda, sem conferir o conteúdo. Pode, por exemplo:

- apontar `executavel` para um programa qualquer;
- declarar, em `[clis.<nome>]`, o `comando` (lista de argumentos) de um programa qualquer;
- apontar arquivos que a Forja lê (`arquivo`, `criterios`, `fatos`, `semgrep_config`).

O `forja.toml` do repositório também declara comandos, como os casos do teste diferencial ([teste-diferencial.md](teste-diferencial.md)).

Use `--config` só com um arquivo que você controla e revisa como código, versionado no repositório ou guardado no pipeline. Não use arquivo recebido de fora, nem um que alguém possa alterar sem revisão.

## Prevenção de suspensão

Só no Windows. A Forja pede ao sistema que não entre em suspensão (`SetThreadExecutionState` com `ES_CONTINUOUS | ES_SYSTEM_REQUIRED`) antes de rodar a execução, nova ou retomada, e devolve o comportamento normal ao sair, em qualquer saída: fim normal, interrupção ou erro (`cli\awake.py::keep_awake`).

- `ES_SYSTEM_REQUIRED` mantém o sistema acordado. Não mantém a tela acesa: ela pode apagar.
- O pedido vale para a thread que o fez. A execução roda numa thread só, então o pedido e a devolução são da mesma thread.
- Se o sistema recusar o pedido, a Forja não diz que pediu e não devolve nada.
- Fora do Windows, a Forja não pede nada e não diz que pediu.
- A proteção cobre a execução, não a preparação nem a confirmação.
