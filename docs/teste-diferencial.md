# Teste diferencial (gate 11)

O gate 11 tem um check, `differential`, em **modo observação**: o resultado aparece no resumo e não bloqueia a tarefa até você promovê-lo, como descrito em [segurança e dependências](seguranca-e-dependencias.md#promover-para-bloqueio) (aqui a seção é `[checks.differential]`). Se a Forja não conseguir medir, o resultado vira premissa no resumo.

Ele só vale em **refatoração**. Em correção, criação e investigação o comportamento muda de propósito, e a Forja nem mede a base do diferencial.

A ideia: para as mesmas entradas, a versão nova do código tem de dar as mesmas saídas que a versão antiga, sem ficar sensivelmente mais lenta nem mais pesada.

## Os casos são seus

A Forja não traz caso nenhum e não inventa um. Você os declara no `forja.toml` do repositório, em `[[differential.cases]]`:

```toml
[[differential.cases]]
name = "relatorio-mensal"
command = ["python", "-m", "meuapp.relatorio", "--mes", "2024-01"]
cwd = "app"
stdin = "tests/entradas/relatorio.json"
outputs = [
  { kind = "stdout", rule = "ignore", ignore = ["^Gerado em "] },
  { kind = "file", path = "saida/relatorio.json", rule = "json" },
  { kind = "exit_code" },
]
```

| Campo | Obrigatório | O que é |
| --- | --- | --- |
| `name` | sim | Palavras em minúsculas, dígitos, `-` e `_`, começando por letra ou dígito. Único em todas as camadas de configuração. |
| `command` | sim | Lista com o programa e os argumentos. **Não é texto de shell**: `sh`, `bash`, `zsh`, `dash`, `ksh`, `fish`, `cmd`, `powershell` e `pwsh` como programa são recusados, com ou sem caminho e `.exe`. |
| `cwd` | não | Diretório de execução, relativo à raiz do repositório, com `/`. Vazio é a raiz. |
| `stdin` | não | Arquivo do repositório entregue na entrada padrão. Sem ele, o comando não recebe entrada. |
| `outputs` | não | O que comparar (abaixo). Sem ele, o caso compara `stdout` e `exit_code`, byte a byte. |

Caminhos são relativos ao repositório, sem `..`, sem barra de volta e sem unidade de disco. Os casos de todas as camadas de configuração (perfil do usuário, repositório, execução) somam-se na ordem de leitura. Chave desconhecida recusa a configuração.

### O que se compara e por qual regra

Cada item de `outputs` tem um `kind` e, opcionalmente, uma `rule`:

| `kind` | O que é | Regras aceitas |
| --- | --- | --- |
| `stdout` | A saída padrão do comando | `bytes`, `json`, `ignore` |
| `exit_code` | O código de saída, em texto decimal | só `bytes` |
| `file` | Um arquivo que o comando escreve, em `path` (relativo ao repositório) | `bytes`, `json`, `ignore` |

| `rule` | Quando as saídas são iguais |
| --- | --- |
| `bytes` (padrão) | Os bytes são idênticos. `\r\n` e `\n` diferem. |
| `json` | Os dois lados são o mesmo documento JSON: ordem das chaves e espaços não contam; ordem de lista e tipo contam (`true`, `1` e `"1"` são diferentes). Saída que não é JSON válido, em qualquer lado, é diferença. |
| `ignore` | Depois de descartar as linhas em que alguma das expressões regulares de `ignore` **encontra** casamento em qualquer ponto, os bytes restantes são idênticos. `ignore` é obrigatório com essa regra e proibido nas outras. Expressão que casa com texto vazio é recusada, porque descartaria todas as linhas. |

Não existe outra regra. **Diferença que nenhuma regra declarada desculpa é diferença.** Código de saída diferente de zero não é falha do caso: é um valor, comparado como os outros. Um `kind` repetido (mesmo `path`, no caso de `file`) no mesmo caso é recusado. `path` só existe em `file`, e `file` o exige.

Arquivo que não existe nos dois lados é igual; existir só em um lado é diferença. Arquivo que é link simbólico, ou que sai da árvore do repositório, conta como ausente.

## O que a Forja faz

1. **Base.** Na medição da base (o commit de partida), cada caso roda **duas vezes**. A Forja guarda as saídas da primeira, o tempo e o pico de memória das duas, e copia o arquivo de `stdin` para **fora** da worktree, uma vez. Se as duas execuções diferem em alguma saída **pela regra do próprio caso**, o caso é não determinístico e vai para **quarentena**: fica inteiro de fora do julgamento e nunca reprova a tentativa. Se todos os casos ficam em quarentena, o check não se aplica (não aprova). A base é gravada em `<dados da execução>\measure\differential\` e relida numa execução retomada.
2. **Cada tentativa.** Cada caso roda `runs` vezes (padrão 3) na worktree da tentativa, com o `stdin` congelado da base. Os casos vêm da política congelada na confirmação, nunca da worktree: o implementador não pode editar um caso, nem sua entrada, para silenciar uma diferença.
3. **Reprova** quando:
   - uma saída difere da base pela regra do caso (um achado por caso e saída, qualquer que seja a execução em que apareceu). A mensagem diz o byte e a linha da primeira divergência e o tamanho dos dois lados, **nunca o conteúdo**;
   - a **mediana** dos tempos das execuções novas passa de `max_time_ratio` vezes a mediana da base;
   - a mediana do pico de memória passa de `max_memory_ratio` vezes a da base.

A comparação de tempo e de memória é por razão entre medianas, não por valor absoluto: uma execução numa máquina ocupada move um valor, não a mediana. A mediana de duas medidas da base é a média delas. Base com mediana de tempo zero não julga tempo.

### Limiares

Os limiares são por linguagem e valem, até a calibração, como palpite:

| Limiar | Padrão | Quer dizer |
| --- | --- | --- |
| `max_time_ratio` | 1,25 | tempo novo acima disso do tempo da base reprova |
| `max_memory_ratio` | 1,25 | pico de memória novo acima disso do da base reprova |
| `runs` | 3 | execuções por caso em cada tentativa (mínimo 1) |

```toml
[checks.differential.thresholds.python]
max_time_ratio = 1.5
runs = 5
```

Um caso não pertence a uma linguagem. Vale o limiar **mais folgado** entre as linguagens do projeto, para não reprovar por um limiar de linguagem que o caso não usa. Valor que não é número maior que zero é ignorado e vale o padrão.

### Execução

O comando roda pelo mesmo executor das demais ferramentas (Job Object, ambiente filtrado), dentro da armadilha de proxy do gate 6, com o mesmo ambiente de modo offline. O que isso é e o que não é está em [E2E com rede desligada](e2e-e-dados-de-teste.md#como-a-rede-é-desligada-e-o-que-isso-não-é). O tempo máximo de cada execução é o da chave `differential`; a sessão ainda não lê tempos da política, então vale o padrão de 300 segundos.

## Quando não conclui

O check devolve resultado inconclusivo, e o resumo o registra como premissa, quando:

- um caso não tem medida na base (por exemplo, a base foi medida com outro conjunto de casos);
- o comando não termina sozinho (estouro de tempo, não iniciou, foi parado) ou o `cwd` não é um diretório da worktree;
- um arquivo de `stdin` falta na base, é diretório, está fora da árvore ou é link simbólico (a base fica com o problema `differential: …`).

Uma reprovação de outro caso vale mais que uma execução que não pôde ser feita.

## O que o resumo diz

- Sem casos: **“Teste diferencial não executado: sem casos (seção [[differential.cases]])”**, na preparação e na entrega. Nunca é aprovação.
- Com casos: “Teste diferencial: I/O não é medido; só tempo e memória, e só onde a plataforma mede.”
- Casos em quarentena e casos sem medida de memória, com os nomes (até 10, cortados em 40 caracteres, e a contagem inteira). A nota vem do log da execução, e por isso sai igual numa execução retomada.

A barra de progresso da interface não mostra o gate 11: com o nome a segunda linha passa de 120 colunas.

## Limites conhecidos

- **I/O não é medido.** Só tempo e memória.
- **Memória só no Windows.** Lá é lido `PeakJobMemoryUsed` do Job Object: o pico da soma do que a árvore de processos segurou ao mesmo tempo. A documentação da Microsoft não diz se é memória comprometida ou residente; como o gate compara duas medidas do mesmo campo, a razão não depende disso. Em Linux e macOS a medida não foi construída: o caso é julgado só por saídas e tempo, e o resumo o diz. A plataforma sem medida devolve “sem medida”, nunca zero.
- **A saída padrão chega por linhas.** Vem do log do executor, que parte em linhas: `\r\n` chega como `\n` e a última linha sempre ganha `\n`, nas duas versões do mesmo modo. Diferença só de fim de linha na saída padrão não é vista.
- **Rede tentada não é registrada.** A armadilha recusa o acesso, mas o destino que o comando tentou alcançar não entra no resultado deste gate (o gate 6 o registra).
- **Caso em quarentena fica inteiro de fora**, mesmo que só uma de suas saídas seja instável. Declare `ignore` ou `json` para as saídas que variam e o caso volta a valer.
- **Só rodam as saídas declaradas.** Efeito colateral que não está em `outputs` não é comparado.
- **O diferencial também roda** nas etapas do documentador e do autor de testes extra, e custa `runs` execuções de cada caso em cada tentativa.
- **A comparação só vale para saídas determinísticas.** O que não for precisa de regra declarada ou fica em quarentena.
- Os limiares são palpite até a calibração (fila 6 do plano de execução).
