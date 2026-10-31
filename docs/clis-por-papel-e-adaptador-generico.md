# CLIs por papel e adaptador genérico

Uma execução da Forja usa uma CLI de agente por papel. Este documento diz quais papéis têm escolha própria, como a Forja sugere uma CLI diferente para o autor de testes e como descrever uma CLI que a Forja não conhece.

## CLIs por papel

| Papel | CLI | Chaves no `execucao.toml` | Flags |
| --- | --- | --- | --- |
| Implementador | `cli` | `executavel`, `modelo` | `--cli`, `--modelo` |
| Autor de testes (só em `corrigir` e `criar`) | `cli_testes` | `executavel_testes`, `modelo_testes` | `--cli-testes`, `--modelo-testes` |
| Documentador, especificador e arqueólogo | a do implementador | não têm escolha própria | não têm |

As CLIs conhecidas são `claude-code`, `codex`, `cursor` e `grok` (`executors\__init__.py::KNOWN_CLIS`). `claude-code` é a padrão. A Gemini CLI está suspensa e fora dessa lista.

### Onde fica o executável de cada CLI

A Forja procura o executável nesta ordem, e usa o primeiro que achar:

1. `executavel` (ou `executavel_testes`) no `execucao.toml`;
2. a variável de ambiente `FORJA_EXECUTOR_<NOME>`, com o nome da CLI em maiúsculas e `_` no lugar de caracteres que não são letras ou números (`claude-code` vira `FORJA_EXECUTOR_CLAUDE_CODE`);
3. a tabela `executaveis` do perfil do usuário (`config.toml`), que liga o nome da CLI ao caminho;
4. a busca no `PATH`.

Um caminho dado nas opções 1 a 3 precisa existir. Se não existir, a Forja não cai para outra fonte e levanta `ExecutorNotFound`; não encontrei, na camada de comando, tratamento que o transforme em mensagem. Se a busca achar mais de uma instalação, a Forja pergunta; sem terminal, ela recusa e pede `executavel` (ver [modo-ci.md](modo-ci.md)).

## Sugestão de autor de testes diferente

Quando a execução escreve testes (`corrigir` ou `criar`) e o autor de testes não foi dado em outra CLI, a Forja sugere, no resumo da preparação, uma CLI conhecida diferente que esteja instalada:

> sugestão: codex também está instalada; um agente de outra CLI nos testes dá mais diversidade de autor (`--cli-testes` ou `cli_testes` no execucao.toml)

Limites da sugestão:

- É só texto. Não muda a escolha de CLI, a configuração nem o `execucao.toml`.
- Não aparece em `refatorar` nem em `investigar`, que não têm autor de testes.
- Não aparece quando o autor de testes já é outra CLI. Com a mesma CLI e outro modelo (`modelo_testes`), a sugestão aparece, porque o autor ainda é a mesma CLI.
- Vale a instalação encontrada: a Forja procura o executável e não faz a prova de vida da outra CLI. A prova só roda na CLI escolhida.
- Só olha as CLIs conhecidas. Uma CLI descrita pelo adaptador genérico não entra na sugestão.
- Nenhuma CLI diferente instalada, nenhuma sugestão.

## Adaptador genérico: `[clis.<nome>]`

Uma CLI que a Forja não conhece pode ser descrita só por dados: como chamá-la e de que ambiente ela precisa. Não é preciso escrever código. A descrição usa o adaptador de modelo de comando (`core\adapters\executor.py::TemplateExecutorAdapter`).

### Onde declarar

- No perfil do usuário, `config.toml` na pasta de configuração da Forja. No Windows é `%APPDATA%\forja\config.toml`. `FORJA_CONFIG_HOME` troca a pasta. Fora do Windows é `$XDG_CONFIG_HOME/forja/config.toml`, ou `~/.config/forja/config.toml` se a variável não existir.
- No `execucao.toml`, na mesma tabela.

Se o mesmo nome aparece nos dois, vale o do `execucao.toml`, e ele substitui a descrição do perfil inteira, campo a campo não se mistura.

### Campos

| Campo | Tipo | Padrão | O que faz |
| --- | --- | --- | --- |
| `comando` | lista de textos, pelo menos 1 item | obrigatório | Argumentos da chamada, com os marcadores abaixo |
| `pacote_por_stdin` | verdadeiro ou falso | `false` | Se `true`, o pacote do papel vai pela entrada padrão, não pelo marcador `{package}` |
| `executaveis` | lista de textos | vazio: o nome da CLI | Nomes do executável que a busca no `PATH` procura |
| `versao` | lista de textos | `["--version"]` | Argumentos que a Forja passa ao executável para ler a versão |
| `ambiente` | lista de textos | vazio | Variáveis de ambiente que a CLI pode ver, além das genéricas |

As variáveis genéricas que toda CLI descrita recebe são `APPDATA`, `LOCALAPPDATA`, `COMSPEC`, `PATHEXT`, `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, `NODE_EXTRA_CA_CERTS` e `SSL_CERT_FILE`. O campo `ambiente` acrescenta a elas.

### Marcadores em `comando`

| Marcador | Vira |
| --- | --- |
| `{executable}` | Caminho do executável escolhido |
| `{package}` | Caminho do arquivo com o pacote do papel |
| `{cwd}` | Diretório de trabalho do agente (a cópia dele) |
| `{role}` | Nome do papel |

Outro marcador é recusado. Um modelo sem `{package}` e sem `pacote_por_stdin = true` também é recusado, porque o agente não receberia o pacote.

### Exemplo

Exemplo de formato, não de uma CLI real:

```toml
[clis.minha-cli]
comando = ["{executable}", "run", "--cwd", "{cwd}", "--role", "{role}", "--arquivo", "{package}"]
versao = ["--version"]
executaveis = ["minha-cli"]
ambiente = ["MINHA_CLI_HOME"]
```

Com a descrição acima, `cli = "minha-cli"` no `execucao.toml` escolhe a CLI. Para receber o pacote pela entrada padrão, troque `{package}` por `pacote_por_stdin = true` e remova o argumento.

### Nomes que a Forja recusa

Um nome de CLI conhecida (`claude-code`, `codex`, `cursor`, `grok`) não pode ser usado em `[clis.<nome>]`. A Forja recusa e diz qual é o nome em conflito. O adaptador conhecido lê os eventos e as permissões dessa CLI, e um modelo com o mesmo nome o substituiria sem aviso. A Gemini CLI não está nessa lista, porque está suspensa; por isso o nome `gemini` passa.

### O que acontece na execução

- **Prova de vida.** A Forja pede à CLI que crie `probe.txt` com o conteúdo `forja-ok`. Só isso é verificado. Nenhum tipo de evento é exigido da saída.
- **Saída.** Cada linha não vazia da CLI aparece como texto. A Forja não lê eventos estruturados nem consumo de tokens dessa CLI.
- **Retomada.** O modelo usado vai para o log da execução (`ExecutorRef.template`). Uma execução retomada usa o modelo gravado, não o que está no perfil no momento.
- **`--config`.** A Forja grava no `execucao.toml` da execução só os modelos que essa execução usa, para que `--config` repita a execução mesmo sem o perfil.
- **Erro no modelo.** Um modelo inválido levanta `ValueError` quando o adaptador é montado (`TemplateExecutorAdapter.__post_init__`). Não encontrei tratamento desse erro que o transforme em mensagem da Forja, então hoje ele aparece como exceção.

## Limites

- **Sem permissão por papel.** A CLI genérica não restringe o que o agente faz em cada papel. O resumo da execução registra a limitação (`A CLI ... não garante as permissões do papel`). Os gates continuam lendo o que a tentativa mudou, mas a Forja não impede a CLI de fazer outras coisas.
- **Prova de vida mínima.** Só o arquivo `probe.txt` é verificado. Uma CLI que responda mal às outras tarefas passa na prova.
- **Saída como texto.** Não há eventos, erros nem consumo estruturados. O que a CLI imprime é só mostrado.
- **`--config` só com arquivo confiável.** O `comando` executa um programa qualquer. Veja a seção de arquivo em que se confia em [modo-ci.md](modo-ci.md).
- **Perfil e `execucao.toml`.** O mesmo nome nos dois vale o do `execucao.toml`, inteiro.

A decisão está em [ADR 0033](adr/0033-o-adaptador-generico-de-cli-e-um-modelo-de-comando.md). A sugestão de autor vem da [ADR 0023](adr/0023-a-forja-e-agnostica-de-cli-uma-por-papel-e-a-diversidade-de-autor-e-so-uma-sugestao.md).
