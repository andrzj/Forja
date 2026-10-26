# Especificar, investigar e criar

Três objetivos usam os papéis do incremento 6: o **especificador** (escreve critérios de aceite), o **arqueólogo** (responde uma pergunta sobre o código, com citações) e o **andaime** (cria o projeto vazio de uma linguagem). Mais o registro de **fatos** que você mantém e a **coleta da revisão**, que diz o que de uma execução chegou à branch principal.

Os dois papéis novos rodam como o documentador: CLI do implementador, cópia sem `.git`, pacote redigido, sem comandos e sem escrever no repositório. Qualquer arquivo que eles alterem reprova no escopo. Eles respondem em `saida.json`; quem grava o artefato (`criterios.json`, `achados.json`) é a Forja, no armazenamento de artefatos da execução, e a etapa termina sem diff e sem commit.

## `forja corrigir` sem critérios

`forja corrigir "<defeito>"` (ou `-f arquivo`) sem `--criterios` e sem `criterios.json` ao lado do `-f` ganha a etapa do especificador antes do autor de testes. Com `--criterios`, o especificador não roda: os critérios são seus.

A entrada é cortada em **elementos** com id estável (`E1`, `E2`…): cada item de lista e cada parágrafo é um elemento; título sozinho não conta. O especificador devolve:

- `criteria`: critérios numerados, cada um com nível (unitário, integração ou E2E) e a lista de ids de elementos de onde veio;
- `left_out`: elemento que não será construído, com o motivo e a evidência que faltou (vira premissa);
- `claims` e `assumptions`, como qualquer papel.

O gate de saída confere o escopo (nada alterado), as citações e a **rastreabilidade**: elemento sem critério, critério com origem inexistente e elemento deixado de fora que não existe são apontados. Resposta sem critério, ou com ids repetidos, é recusada de verdade. Os critérios seguem para o autor de testes, que entrega o **manifesto de testes** (critério → teste, e geradores de dados com semente); o resumo mostra a cadeia elemento → critério → teste na seção “Rastreabilidade”.

E2E declarado inviável não tem campo próprio: o especificador o diz em `assumptions` e a premissa vai ao resumo.

## `forja investigar`

```bash
forja investigar "como o pedido chega ao estoque?"
```

A tarefa é `arqueólogo → documentador`. O arqueólogo responde com `claims` (cada uma com citação) e `assumptions` (o que adivinhou). Resposta sem claim e sem premissa é recusada. O gate de saída confere o escopo e as citações. A Forja classifica cada afirmação:

| Rótulo | Quando |
| --- | --- |
| provado | a citação confere por máquina: arquivo e linhas existem, ou a evidência foi medida |
| confirmado | cita um fato que você registrou |
| premissa | o que o agente declarou como suposição; entra no resumo com o nome estável |

O documentador recebe as três listas e escreve em `docs/`, sem transformar premissa em afirmação. O registro de mudança sai sem código, porque a tarefa não alterou código. Com `execucao.toml`: `objetivo = "investigar"`, a pergunta em `descricao`. O verbo `documentar` saiu da ajuda: documentação já é a etapa final de todo objetivo.

## `forja criar`

```bash
forja criar "um conversor de moedas de linha de comando"
```

Roda num diretório vazio (no máximo com `.git`). A linguagem não tem padrão: sem pessoa para perguntar, ela vem de `linguagem` no `execucao.toml`; o nome sugerido é o do diretório (`nome` muda). Linguagens com modelo: Python, Go, TypeScript, C# e Java. JavaScript não tem modelo.

| Linguagem | O que o modelo escreve |
| --- | --- |
| Python | `pyproject.toml`, `src/<pacote>`, `tests/` com um teste que passa |
| Go | `go.mod` e um `*_test.go` |
| TypeScript | `package.json`, `tsconfig.json`, vitest; `setup`: `npm install` |
| C# | `.sln`, o projeto e o projeto de teste |
| Java | `pom.xml`, `src/main/java`, `src/test/java` |

O modelo é dado do adaptador, escrito sem modelo de linguagem. **O andaime roda depois do seu “sim”**: escreve os arquivos, faz `git init`, o commit `chore: scaffold <linguagem> project <nome>` (autor `Forja (andaime)`) e roda o `setup` do modelo, com limite de 900 s. Depois disso o repositório é existente e o fluxo é o de funcionalidade: especificador → autor de testes → implementador → documentador. Build e testes verdes do modelo são medidos como a linha de base da execução.

Limites: `npm install` e o download de JUnit e NuGet precisam de rede; a Forja só diz o que falta. Se o `setup` falha, o projeto fica criado e comitado e a mensagem diz isso. As chamadas git do andaime ignoram hooks e `fsmonitor` de um `.git` que já existia.

## Fatos

Um arquivo de texto seu, uma linha por fato; linhas em branco e as que começam com `#` são ignoradas:

```text
f1 | maria | 2026-10-26 | o estoque é baixado pelo worker, não pela API
f2 | maria | 2026-10-26 | o prazo de 30 dias vale só para B2B | corrige:p3a9c01de
```

Campos: `id`, autor, data (`AAAA-MM-DD`), texto e, se o fato resolve uma premissa do resumo, `confirma:<id>` ou `corrige:<id>` (o id é o `p` com 8 letras e números que o resumo mostra). Aponte o arquivo com `--fatos` ou `fatos` no `execucao.toml`. Linha malformada recusa a execução e diz qual. Os fatos entram no pacote de todo papel como evidência, podem ser citados (gate 13) e o resumo marca a premissa resolvida como “Confirmada por” ou “Corrigida por”.

**A Forja não guarda fatos entre execuções:** o arquivo é seu, e o `execucao.toml` lembra o caminho.

## `forja revisao`

```bash
git fetch
forja revisao [<execução>] [--principal origin/main] [--fatos comentarios.txt]
```

Só lê: não inicia execução e não altera o repositório. Lê o log da execução (a mais recente do repositório, ou a dada) e os commits `<commit de partida>..<principal>` (padrão `origin/HEAD`; sem ele, passe `--principal`), casando por `Stage-Id` e `Task-Id`. O relatório vai para `<dados>\revisoes\<execução>.md`:

- por tarefa e etapa, se chegou à principal (inteira, em parte ou não);
- commits de estilo e commits só com `Task-Id`, contados e não interpretados;
- tabelas por papel, CLI e tipo de tarefa, e por gate;
- os comentários do arquivo de fatos, ligados às premissas que confirmam ou corrigem, e as premissas sem resposta.

## Gates

| Check | Gate | Modo | Reprova |
| --- | --- | --- | --- |
| `traceability` | 13 | observação | elemento sem critério, critério com origem inexistente, elemento deixado de fora que não existe |
| `citations` | 13 | observação, bloquear se não medir | citação de arquivo ou linhas inexistentes, métrica desconhecida ou fato não registrado; vale para todo papel que declare claims |
| `scope` | 1 | bloqueante | qualquer arquivo alterado pelo especificador ou pelo arqueólogo |

## Limites conhecidos

- A rastreabilidade garante que cada elemento tem critério e cada critério tem origem; que o critério diga o que o elemento diz é da revisão. Prosa corrida vira poucos elementos grandes e a rastreabilidade fica grossa.
- O gate 13 confere que a citação existe e cabe no arquivo, não que o trecho sustenta a afirmação.
- As instruções do implementador e do autor de testes não pedem claims; o gate só olha o que declararem. A origem dos critérios de `--criterios` é texto seu e não é conferida.
- Squash ou rebase feito por você apaga os trailers `Stage-Id` e `Task-Id`; a coleta só responde sobre o que o git ainda mostra. Ids de etapa se repetem entre execuções que partiram do mesmo commit.
- Especificador e arqueólogo não commitam; por isso não aparecem como commits na coleta.
- Os testes cobrem os papéis com agentes roteirizados e ferramentas falsas. Execução viva e E2E reais são do dono (fila 8).
