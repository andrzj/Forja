# Teste diferencial (gate 11)

O gate 11 tem um check, `differential`. Para as mesmas entradas, a versão nova do código tem de dar as mesmas saídas que a versão antiga, sem ficar sensivelmente mais lenta nem mais pesada. A lista de todos os gates está em [README.md](README.md).

| Item | Valor |
| --- | --- |
| Id da verificação | `differential` |
| Modo padrão | `observation` (mede e reporta, não bloqueia) |
| `on_inconclusive` padrão | `premise` (a lacuna vai para o resumo como suposição) |
| Quando roda | só em `forja refatorar` |
| Nome na barra de gates | `diferencial` |
| Linguagens | qualquer: o comando de cada caso é seu. Só os limiares são por linguagem (`java`, `go`, `python`, `csharp`, `javascript`, `typescript`) |

Em correção, criação e investigação o comportamento muda de propósito, então a Forja não mede a base do diferencial nelas e não mostra aviso algum.

## O que mede

| Medida | Como é julgada |
| --- | --- |
| Saída | cada saída declarada (saída padrão, código de saída, arquivo) tem de ser igual à da base pela regra do caso |
| Tempo | a mediana dos tempos da versão nova, dividida pela mediana da base, não pode passar de `max_time_ratio` |
| Memória | o mesmo, com o pico de memória e `max_memory_ratio` |

Entrada e saída de disco ou de rede não são medidas. A comparação é por razão entre medianas, não por valor absoluto: uma execução feita numa máquina ocupada move um valor, não a mediana. A base tem duas medidas, e a mediana de duas é a média delas. Base com mediana de tempo zero não julga tempo.

A memória é medida nas três plataformas, cada uma a seu modo. No Windows vem do contador do Job Object (o pico da soma do que a árvore de processos segurou ao mesmo tempo). Em Linux e macOS a Forja soma a memória residente de todos os processos do grupo a cada 50 ms e o pico é a maior soma; um pico mais curto que o intervalo pode passar despercebido. Como a Forja compara duas medidas feitas do mesmo modo, a razão vale. Uma execução sem medida de memória não entra na mediana, e um caso sem nenhuma medida de memória na base não tem a memória julgada.

## Os casos são seus

A Forja não traz caso nenhum e não inventa um. Você os declara no `forja.toml` do repositório, em `[[differential.cases]]`. Sem casos, o gate não roda, e num refatoramento o resumo traz, na preparação e na entrega, o aviso `Teste diferencial não executado: sem casos (seção [[differential.cases]]).` Isso nunca é aprovação.

### Um caso mínimo

```toml
# Roda o programa na versão antiga e na nova e compara a saída padrão
# e o código de saída, byte a byte (o padrão quando não há `outputs`).
[[differential.cases]]
name = "ajuda"
command = ["python", "-m", "meuapp", "--ajuda"]
```

### Um caso completo

```toml
[[differential.cases]]
name = "relatorio-mensal"
command = ["python", "-m", "meuapp.relatorio", "--mes", "2024-01"]
cwd = "app"                             # roda em app/, a partir da raiz do repositório
stdin = "tests/entradas/relatorio.json" # esse arquivo vira a entrada padrão do programa
outputs = [
  # ignora a linha que traz a hora da geração; o resto tem de ser idêntico
  { kind = "stdout", rule = "ignore", ignore = ["^Gerado em "] },
  # o arquivo escrito pelo programa é comparado como documento JSON
  { kind = "file", path = "saida/relatorio.json", rule = "json" },
  # o código de saída é comparado como texto decimal
  { kind = "exit_code" },
]
```

### Campos do caso

| Campo | Obrigatório | O que é |
| --- | --- | --- |
| `name` | sim | Letras minúsculas, dígitos, `-` e `_`, começando por letra ou dígito. Único no arquivo. |
| `command` | sim | Lista com o programa e os argumentos. Não é texto de shell: `sh`, `bash`, `zsh`, `dash`, `ksh`, `fish`, `cmd`, `powershell` e `pwsh` como programa são recusados, com ou sem caminho e `.exe`. |
| `cwd` | não | Diretório de execução, relativo à raiz do repositório, com `/`. Sem ele, vale a raiz. |
| `stdin` | não | Arquivo do repositório entregue na entrada padrão. Sem ele, o comando não recebe entrada. |
| `outputs` | não | O que comparar (próxima seção). Sem ele, o caso compara `stdout` e `exit_code`, os dois por `bytes`. Se aparecer, não pode ser vazio. |

Caminhos (`cwd`, `stdin`, `path`) são relativos ao repositório, com `/`, sem `..`, sem barra de volta e sem unidade de disco. Chave desconhecida recusa a configuração. As mensagens de erro e o formato geral do arquivo estão em [forja.toml](../forja-toml.md).

### O que se compara e por qual regra

Cada item de `outputs` tem um `kind` e, opcionalmente, uma `rule`:

| `kind` | O que é | Regras aceitas |
| --- | --- | --- |
| `stdout` | a saída padrão do comando (a saída de erro não é comparada) | `bytes`, `json`, `ignore` |
| `exit_code` | o código de saída, em texto decimal | só `bytes` |
| `file` | um arquivo que o comando escreve, em `path` | `bytes`, `json`, `ignore` |

| `rule` | As saídas são iguais quando |
| --- | --- |
| `bytes` (padrão) | os bytes são idênticos. `\r\n` e `\n` diferem. |
| `json` | os dois lados são o mesmo documento JSON: ordem das chaves e espaços não contam; ordem de lista e tipo contam (`true`, `1` e `"1"` são diferentes). Saída que não é JSON válido, em qualquer lado, é diferença. |
| `ignore` | depois de descartar as linhas em que alguma das expressões de `ignore` encontra casamento em qualquer ponto, os bytes restantes são idênticos. |

Regras de forma:

- `ignore` (a lista de expressões regulares) é obrigatório e não vazio com `rule = "ignore"`, e proibido nas outras regras. Uma expressão que casa com texto vazio é recusada, porque descartaria todas as linhas.
- `path` é obrigatório em `file` e proibido nos outros tipos.
- Um mesmo `kind` repetido no mesmo caso é recusado (em `file`, o par `kind` e `path`).

Não existe outra regra. Uma diferença que nenhuma regra declarada desculpa é uma diferença. Código de saída diferente de zero não é falha do caso: é um valor, comparado como os outros.

Um arquivo que não existe nos dois lados é igual; existir só num lado é diferença. Arquivo que é link simbólico ou que sai da árvore do repositório conta como ausente.

## O que a Forja faz

1. **Base.** Uma vez por execução, no commit de partida, cada caso roda duas vezes. A Forja guarda as saídas da primeira, o tempo e o pico de memória das duas, e copia o arquivo de `stdin` para fora da cópia de trabalho. Se as duas execuções diferem em alguma saída pela regra do próprio caso, o caso é não determinístico e vai para quarentena: fica inteiro de fora do julgamento e nunca reprova a tentativa. Se todos os casos ficam em quarentena, o check não se aplica (não aprova). A base fica nos dados da execução e é relida numa execução retomada.
2. **Cada tentativa.** Cada caso roda `runs` vezes (padrão 3) na cópia de trabalho da tentativa, com o `stdin` congelado da base. Os casos vêm da política congelada na confirmação, nunca da cópia de trabalho: o agente não consegue editar um caso, nem a entrada dele, para silenciar uma diferença.
3. **Reprova** quando:
   - uma saída difere da base pela regra do caso (um achado por caso e saída, em qualquer das execuções). A mensagem diz o byte e a linha da primeira divergência e o tamanho dos dois lados, nunca o conteúdo;
   - a mediana dos tempos das execuções novas passa de `max_time_ratio` vezes a mediana da base;
   - a mediana do pico de memória passa de `max_memory_ratio` vezes a da base.

As mensagens dos achados saem em inglês, como as demais mensagens técnicas da Forja. O achado de saída diz `the output differs from the base: differs at byte N (line L); the base has X bytes, the new version Y`, e os de custo dizem `slower than the base` ou `uses more memory than the base`, com a razão medida e o limite.

### Execução do comando

O comando roda pelo mesmo executor das demais ferramentas (processos presos à Forja, ambiente filtrado), dentro da armadilha de proxy do gate 6 e com as mesmas variáveis de modo offline. O que isso garante e o que não garante está em [ponta a ponta e dados de teste](e2e-e-dados-de-teste.md#como-a-rede-é-desligada-e-o-que-isso-não-é). A rede que o comando tentou alcançar não entra no resultado deste gate; o gate 6 a registra. As variáveis de ambiente que a Forja repassa estão em [ambiente](../ambiente.md).

Cada execução tem tempo máximo de 300 segundos. Esse valor é fixo: a política não o altera. Quem passar disso dá resultado inconclusivo (veja abaixo).

### Limiares

Os limiares são por linguagem e são palpites, sem calibração por medição.

| Limiar | Padrão | Quer dizer |
| --- | --- | --- |
| `max_time_ratio` | `1.25` | tempo novo acima disso vezes o da base reprova |
| `max_memory_ratio` | `1.25` | pico de memória novo acima disso vezes o da base reprova |
| `runs` | `3` | execuções por caso em cada tentativa; a parte decimal é descartada e o mínimo é 1 |

Um caso não pertence a uma linguagem. Vale o limiar mais folgado entre as linguagens do projeto, e uma linguagem sem valor no arquivo entra com o padrão. Para apertar um limite num projeto com duas linguagens, defina-o nas duas. Valor que é zero ou negativo é ignorado e vale o padrão; valor que não é número finito é erro de configuração, como em qualquer limiar.

```toml
# Projeto só em Python: tolera 50% a mais de tempo e roda cada caso 5 vezes
# na tentativa. O limite de memória continua em 1.25.
[checks.differential.thresholds.python]
max_time_ratio = 1.5
runs = 5
```

```toml
# Projeto com duas linguagens: para valer 1.1 de verdade, defina nas duas.
# Se só uma dissesse 1.1, a outra entraria com 1.25 e este seria o valor usado.
[checks.differential.thresholds.python]
max_time_ratio = 1.1

[checks.differential.thresholds.go]
max_time_ratio = 1.1
```

## Quando não conclui

O check devolve resultado inconclusivo, e o resumo o registra como premissa (com `on_inconclusive = "premise"`, o padrão), quando:

- um caso não tem medida na base (por exemplo, a base foi medida com outro conjunto de casos);
- o comando não termina sozinho (estouro de tempo, não iniciou, foi parado);
- o `cwd` não é um diretório da cópia de trabalho;
- um arquivo de `stdin` falta na base, é diretório, está fora da árvore ou é link simbólico. A base fica com o problema `differential: ...`.

Uma reprovação de outro caso vale mais que uma execução que não pôde ser feita.

## O que o resumo diz

- Sem casos, num refatoramento: `Teste diferencial não executado: sem casos (seção [[differential.cases]]).`
- Com casos: `Teste diferencial: I/O não é medido; só tempo e memória, e só onde a plataforma mede.`
- Os casos em quarentena e os casos sem medida de memória, com os nomes (até 10, cortados em 40 caracteres, mais a contagem inteira). Uma execução retomada traz a mesma nota.

## O que acontece ao falhar

O resultado depende de `mode` e de `on_inconclusive`, como descrito em [forja.toml](../forja-toml.md#modo-e-política-de-inconclusivo):

| Resultado | `mode = "observation"` (padrão) | `mode = "blocking"` |
| --- | --- | --- |
| Aprovado ou não aplicável | passa | passa |
| Reprovado (saída, tempo ou memória) | aparece no relatório e não bloqueia | reprova a tentativa; os achados vão para a tentativa seguinte |
| Inconclusivo | aparece como premissa | `premise`: segue com a lacuna declarada; `block`: bloqueia a tarefa |

## Promover para bloqueio

Para o gate reprovar de verdade, promova o check com uma decisão registrada. O procedimento e o porquê estão em [segurança e dependências](seguranca-e-dependencias.md#promover-para-bloqueio); aqui a seção é `[checks.differential]`.

```toml
# Os casos precisam existir para o gate valer.
[[differential.cases]]
name = "relatorio-mensal"
command = ["python", "-m", "meuapp.relatorio", "--mes", "2024-01"]
outputs = [
  { kind = "stdout", rule = "ignore", ignore = ["^Gerado em "] },
  { kind = "exit_code" },
]

# Promoção: o check nasce em observação, então precisa de data e motivo.
[checks.differential]
mode = "blocking"
promotion = { date = 2030-01-31, reason = "três refatorações seguidas sem falso positivo" }
# Se a medição não puder ser feita, bloqueia em vez de seguir com a lacuna.
on_inconclusive = "block"
```

Sem `promotion`, `mode = "blocking"` é recusado com `promoting a check from observation to blocking needs a recorded decision`.

## Limites conhecidos

- **I/O não é medido.** Só saída, tempo e memória.
- **A saída padrão chega por linhas.** Vem do registro do executor, que parte em linhas: `\r\n` chega como `\n` e a última linha sempre ganha `\n`, nas duas versões. Diferença só de fim de linha na saída padrão não é vista.
- **Caso em quarentena fica inteiro de fora**, mesmo que só uma de suas saídas seja instável. Declare `ignore` ou `json` para as saídas que variam e o caso volta a valer.
- **Só as saídas declaradas são comparadas.** Efeito colateral que não está em `outputs` passa despercebido.
- **A comparação só vale para saídas determinísticas.** O que não for precisa de regra declarada ou fica em quarentena.
- **Custo.** Cada tentativa roda `runs` vezes cada caso.
- **Os limiares são palpites.** Ajuste-os ao seu projeto.
