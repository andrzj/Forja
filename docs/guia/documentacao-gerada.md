# Documentação gerada

Esta página descreve o que a Forja escreve no repositório como documentação, quando escreve, como ajustar e como ver o resultado. Cada comportamento vem com um exemplo comentado. Para a política de cada verificação, veja `forja-toml.md`. Para os gates 12, 13 e 14, veja `gates\README.md`. Para o diário de bordo, veja `diario-de-bordo.md`. Para as opções da linha de comando, veja `comandos.md`.

## O que a Forja escreve e quando

Toda tarefa de `refatorar`, `corrigir`, `criar` e `investigar` termina com uma etapa do documentador. Ela vem depois do implementador (e, em `investigar`, depois do arqueólogo), e a tarefa só é integrada depois do commit `docs:`.

O documentador usa a CLI do implementador, sem comandos e só em arquivos de documentação: o README, arquivos sob `docs/` e outros arquivos Markdown ou reStructuredText. Se ele mexer em código, teste ou configuração, a tentativa é reprovada.

| O quê | Onde | Quem escreve | Quando |
| --- | --- | --- | --- |
| Registro de mudança | `docs/mudancas/<tarefa>.md` | a Forja | em toda tarefa, no commit `docs:` |
| Diário de bordo | `docs/mudancas/<tarefa>-diario.md` | a Forja | em toda tarefa, no commit `docs:` |
| README | `README.md` (ou o README que o repositório já tem) | o agente | só se alguma seção estiver com problema, em commit próprio `docs(readme):`, antes do `docs:` |
| Registro de decisão | `docs/adr/NNNN-<nome>.md` | o agente | só quando a tarefa traz dependência externa ou módulo novo, no commit `docs:` |
| Outros documentos | onde estiverem | o agente | só os que ficaram errados por causa da mudança, no commit `docs:` |

O caminho do registro de mudança (`docs/mudancas`) e o dos registros de decisão (`docs/adr`) são fixos: não há chave para mudá-los nem para o idioma. Um arquivo de `docs/mudancas/` que o agente escreva fora dos dois da própria tarefa é reprovado: o registro é da Forja.

As verificações desta etapa começam em `observation`. O resultado aparece no resumo da execução e não reprova a tentativa. Só `citations` e `change_record` têm `on_inconclusive = "block"`: se a Forja não conseguir medir, a tarefa bloqueia. Para torná-las bloqueantes, veja "Ajustar as verificações".

## Registro de mudança

O arquivo `docs/mudancas/<tarefa>.md` tem duas partes. A primeira, factual, a Forja calcula sozinha:

| Seção | Conteúdo |
| --- | --- |
| título e descrição | o identificador da tarefa e o que foi pedido |
| `## Arquivos` | cada arquivo que a tarefa tocou, como criado, modificado ou removido |
| `## Símbolos` | funções, classes e afins criados, alterados ou removidos. Em toda remoção vem a prova de não uso (se algum outro arquivo ainda cita o nome) e, para símbolo público, o aviso `símbolo público removido` |
| `## Métricas` | cada métrica medida antes e depois |
| `## Gates aprovados` | os gates que a tentativa passou |
| `## Ferramentas` | versões das ferramentas e das CLIs de agente usadas |
| `## Premissas` | o que foi assumido porque a Forja não conseguiu medir |
| `## Para reverter` | o `git revert` do commit da tarefa |

A segunda parte, `## Porquê e impacto`, vem das afirmações do agente. O agente declara cada afirmação com ao menos uma citação (veja "Citações"), e a Forja escreve na seção só as que passaram. Se o agente escrever o arquivo de registro, a Forja o sobrescreve.

Exemplo do que o arquivo traz (valores ilustrativos):

```markdown
# Registro de mudança: t1

reduzir a complexidade de cobrar em src/pagamento.py

## Arquivos

- `src/pagamento.py`: modified

## Símbolos

- `cobrar` (function) em `src/pagamento.py`: modified
- `_desconto_legado` (function) em `src/pagamento.py`: removed; prova de não uso: nenhum outro arquivo menciona o nome

## Métricas

| Métrica | Antes | Depois |
| --- | --- | --- |
| complexity.max | 22 | 9 |

## Gates aprovados

- complexity
- tests

## Ferramentas

- python 3.13.0
- CLI claude-code 2.0.0

## Premissas

Nenhum.

## Para reverter

`git revert 4f2a9c1`

## Porquê e impacto

- A função deixou de aninhar condições para caber no limite de complexidade (`src/pagamento.py:10-31`)
```

A verificação `change_record` (gate 14) reprova o registro ausente, sem uma das seções, sem algum arquivo ou símbolo do diff, ou sem nenhuma afirmação citada. A prova de remoção é busca de texto pelo nome: um nome comum encontra homônimos, e na dúvida o registro sinaliza.

## Diário de bordo

O arquivo `docs/mudancas/<tarefa>-diario.md` traz todas as tentativas da tarefa, as rejeitadas inclusive, e as decisões da Forja. A Forja o escreve no mesmo commit `docs:` do registro. O formato e o que o agente vê dele estão em `diario-de-bordo.md`.

## README

A Forja avalia o README sem modelo e entrega ao documentador a lista do que está errado. O documentador só pode mudar as seções com problema. README sem problema não é tocado. Se o repositório tem README, a mudança sai no commit `docs(readme):`, separado do `docs:`.

O que a verificação `readme` confere:

| Confere | Regra |
| --- | --- |
| existência | o repositório tem um README |
| seções | seis temas: o que é, como construir, como testar, como executar, como configurar, dependências. A Forja reconhece o título por palavras em português ou em inglês |
| comandos | os comandos de construir e testar do README são os que a Forja executa, comparados por programa e subcomando |
| links | links relativos apontam para arquivo que existe, e âncora aponta para título que existe |

Links externos não são conferidos, porque exigiriam rede. O resumo da execução declara isso.

Exemplo de um README com as seis seções que a verificação reconhece:

```markdown
# Meu projeto

Serviço que calcula o frete de um pedido.

## Construir

    uv sync

## Testar

    uv run pytest

## Executar

    uv run python -m frete

## Configurar

Defina `FRETE_REGIAO` no ambiente.

## Dependências

Python 3.12 ou mais novo e `uv`.
```

Os comandos das seções de construir e testar precisam ser os que a Forja executa no projeto. Se o README diz `npm test` e a Forja roda `pytest`, `readme` aponta a divergência e o documentador corrige essa seção.

## Registro de decisão

A Forja decide se uma tarefa deve deixar um registro de decisão. O agente só o redige. A decisão dispara em dois casos:

| Gatilho | Quando |
| --- | --- |
| dependência externa nova | um manifesto da tarefa traz uma dependência que o da base não tinha |
| módulo novo | a tarefa traz um arquivo de produção em um diretório que não tinha nenhum na base |

Mudança no grafo entre módulos e em regra de camada, mesmo detectada pelo gate 9, não dispara o registro.

Disparado o gatilho, a verificação `adr` exige ao menos um arquivo novo `docs/adr/NNNN-<nome>.md`, com número de quatro dígitos ou mais ainda não usado, e com títulos de alternativas e de consequências. Um registro bom basta. Registro a mais não reprova. Sem gatilho, não se pede registro.

Exemplo de arquivo que a verificação aceita (os títulos podem estar em português ou em inglês):

```markdown
# 0007. Envio assíncrono de pedidos com a biblioteca X

## Contexto

O envio de pedidos passou a ser assíncrono.

## Alternativas

- biblioteca X: já usada pelo time
- implementação própria: mais código para manter

## Consequências

- uma dependência externa nova, `x`
- o worker precisa ser iniciado junto do serviço
```

## Documento que cita o que não existe mais

A verificação `doc_drift` procura, nos documentos, citações entre crases que apontam para algo que não existe. Lê só o que está entre crases e fora de blocos de código:

| Citação | Existe se |
| --- | --- |
| caminho | o arquivo ou diretório está no repositório |
| `make <alvo>` | o `Makefile` tem esse alvo |
| `npm run <script>`, `yarn run`, `pnpm run`, `bun run` | o `package.json` tem esse script |
| símbolo | cada parte do nome aparece como palavra em algum arquivo que não seja documentação |

A verificação só conta citação nova: a que o documento não tinha na base da tarefa, ou cujo alvo a tarefa removeu. A deriva que já existia não reprova a tarefa. Os arquivos de `docs/mudancas/` não são lidos, e arquivos acima de 1.000.000 de bytes são pulados. Uma constante ou chave de configuração com o mesmo nome de um símbolo removido esconde a remoção.

```markdown
Para subir o serviço, rode `make servir` e abra `docs/uso.md`.
```

Se o `Makefile` não tem o alvo `servir` ou `docs/uso.md` não existe mais, `doc_drift` aponta a citação.

## Voz

A voz é o jeito de escrever: sem cumprimento, sem elogio, sem falar de si, sem oferta de ajuda. A Forja não bloqueia por voz. Ela instrui o agente e mede o que ele escreveu.

### A instrução

Um texto fixo, em inglês, entra como seção `## Voice` no pacote de toda chamada de agente que escreve texto: implementador, autor de testes, especificador, arqueólogo e documentador. Ele pede para não inventar fato, dizer o simples, seguir o idioma e os hábitos do repositório, deixar código, identificadores e citações como estão, e evitar uma lista de padrões: cumprimento e elogio, falar de si, oferta de ajuda, anúncio de importância, vocabulário inflado, travessões, negrito e títulos em maiúsculas, emoji, voz passiva e texto que narra a mudança em vez de descrevê-la.

Hábito claro do repositório vale mais do que a lista. Se o repositório escreve com emoji ou com travessões, siga-o: desligue o marcador (veja abaixo).

Na CLI `claude-code` o mesmo texto vai também ao prompt de sistema, acrescentado ao padrão da CLI, por um arquivo fora do diff que o agente não pode alterar. Nas outras CLIs o texto chega só pelo pacote.

A instrução acompanha a medida. Uma regra ligada a um marcador sai do texto quando o repositório desliga esse marcador, e os padrões que o repositório acrescenta entram listados no texto. Assim o agente é instruído a evitar o que a medida procura, e só isso.

### A medida

A verificação `voice` (gate 12) lê o que a tentativa acrescenta: linhas novas de documentação, comentários novos de código em Python, Go, Java, C#, JavaScript e TypeScript, e a mensagem de commit. Texto de string no código não conta. O achado diz o arquivo, a linha e o marcador, e nunca copia o texto.

| Marcador | O que marca |
| --- | --- |
| `greeting` | abertura que cumprimenta em vez de dizer algo |
| `self-reference` | o modelo falando de si mesmo |
| `inflated` | vocabulário que infla e não diz nada |
| `announcement` | frase que anuncia que algo importa em vez de dizê-lo |
| `offer` | oferta de mais ajuda |
| `emoji` | emoji em texto que se lê como documentação |
| `repository-N` | o N-ésimo padrão de `markers_extra` |

Além dos marcadores, a verificação conta os travessões longos (U+2014) que um arquivo, ou a mensagem de commit, acrescenta. Acima de `max_dashes` (padrão 3), o achado é reportado. O agente é instruído a não usar nenhum.

`voice` e `comments` nunca aceitam `mode = "blocking"`: um `mode = "blocking"` nelas é erro de configuração.

### Ajustar a voz

```toml
# forja.toml

[voice]
# Este repositório usa emoji na documentação: o marcador sai da medida
# e a regra sai da instrução ao agente.
markers_off = ["emoji"]

# Proíbe, além dos marcadores da Forja, a palavra "sinergia".
# Cada expressão é do Python (re), sem diferenciar maiúsculas de minúsculas,
# e vira o marcador repository-1, repository-2 e assim por diante.
markers_extra = ["\\bsinergia\\b"]

# Nenhum travessão longo tolerado em um arquivo ou na mensagem de commit.
[checks.voice.limits]
max_dashes = 0
```

As listas de `[voice]` somam entre o perfil do usuário e o `forja.toml` do repositório. Um identificador que a Forja não conhece em `markers_off` é ignorado, e a lista continua tão rígida quanto era. O que o repositório desliga ou acrescenta aparece nas notas da preparação da execução:

```text
voz: marcadores desligados pelo repositório: emoji
voz: padrões proibidos pelo repositório: \bsinergia\b
```

A Forja não edita o que o agente escreveu: o ajuste é na medida e na instrução, não na reescrita.

## Comentários

A verificação `comments` (gate 12, observação, nunca bloqueante) lê os comentários novos do código e reporta dois casos:

| Caso | Regra |
| --- | --- |
| comentário que repete o código | ao menos duas palavras com sentido, das quais 75% ou mais estão na linha de código a que o comentário se refere |
| símbolo público novo sem comentário | uma função, classe ou interface pública nova sem comentário acima dela (em Python, sem docstring) |

Os 75% são uma constante da Forja e não têm chave no `forja.toml`. Para silenciar a verificação, não há ajuste além do `mode`, que só admite `observation`.

```python
# soma um ao contador
contador += 1   # repete o código: reportado

# o contador começa em um porque o cabeçalho conta como linha
contador += 1   # explica o porquê: aceito
```

## Citações e fatos

O agente documenta o porquê de uma mudança em afirmações. Cada afirmação precisa de ao menos uma citação, de um destes tipos:

| Tipo | Forma | A verificação `citations` confere |
| --- | --- | --- |
| arquivo | caminho e intervalo de linhas | que o arquivo existe e tem essas linhas |
| evidência | nome de uma métrica ou de uma configuração | que a métrica ou a configuração existe |
| fato | identificador de um fato que você registrou | que o fato existe no arquivo de fatos da execução |

A Forja não sabe se as linhas citadas dizem o que a afirmação diz: isso é do revisor. `citations` (gate 13) vale também para o especificador e o arqueólogo.

Para dar ao agente algo que só você sabe, registre um fato. O formato do arquivo está em `comandos.md`, seção "Fatos":

```text
# fatos do pedido 114
# id | autor | data | texto
f1 | maria | 2030-01-31 | o estoque é baixado pelo worker, não pela API
```

```bash
# Os fatos entram no pacote de todos os agentes e podem ser citados no registro.
forja corrigir "o estoque baixa duas vezes" --fatos fatos.txt
```

Uma afirmação com `fato f1` aparece no registro como `(fato f1)`. Citar um identificador que não está no arquivo reprova a citação. Em `execucao.toml`, a chave `fatos` faz o mesmo que `--fatos`; veja `execucao-toml.md`.

## Ajustar as verificações

Todas as verificações desta página são chaves de `[checks.<id>]` no `forja.toml`: `change_record`, `readme`, `doc_drift` e `adr` (gate 14), `citations` (gate 13), `voice` e `comments` (gate 12). Promover uma delas a bloqueante exige a decisão registrada em `promotion`; o motivo está em `forja-toml.md`.

```toml
# forja.toml

# O README passa a decidir a tentativa: seção com problema reprova.
[checks.readme]
mode = "blocking"
on_inconclusive = "premise"   # se a Forja não conseguir medir, segue com a lacuna declarada
promotion = { date = 2030-01-31, reason = "o README já responde os seis temas" }

# Dependência ou módulo novo sem registro de decisão reprova a tentativa.
[checks.adr]
mode = "blocking"
promotion = { date = 2030-01-31, reason = "o time quer registro de toda decisão estrutural" }

# Afirmação sem citação válida passa a reprovar. Se a Forja não conseguir
# medir, segue com a lacuna declarada em vez de bloquear a tarefa.
[checks.citations]
mode = "blocking"
on_inconclusive = "premise"
promotion = { date = 2030-01-31, reason = "citação inventada não entra no registro" }
```

Valores padrão:

| Verificação | Gate | `mode` | `on_inconclusive` |
| --- | --- | --- | --- |
| `change_record` | 14 | `observation` | `block` |
| `readme` | 14 | `observation` | `premise` |
| `doc_drift` | 14 | `observation` | `premise` |
| `adr` | 14 | `observation` | `premise` |
| `citations` | 13 | `observation` | `block` |
| `voice` | 12 | `observation`, nunca `blocking` | `premise` |
| `comments` | 12 | `observation`, nunca `blocking` | `premise` |

## Ver o resultado

O resumo da execução (`runs/<id>/resumo.md`) tem a seção "Documentação". Para cada tarefa integrada, lista o registro, o README e os registros de decisão deixados e os demais documentos alterados:

```text
## Documentação

- `t1`: registro `docs/mudancas/t1.md`; README: `README.md`; ADR: `docs/adr/0007-envio.md`; outros: `docs/uso.md`.

Não conferido: links externos do README (exigiriam rede). O texto que o agente escreveu fora das afirmações com citação só passa pelas verificações de tópico.
```

O que uma verificação mediu e não pôde concluir aparece em "Premissas assumidas", no mesmo resumo e na seção `## Premissas` do registro. O resumo também diz quem documentou: "o mesmo que implementa, sem comandos e só em documentação". Para ler a execução depois do `git fetch`, use `forja revisao`.

## O que a Forja não confere

- Se as linhas citadas dizem o que a afirmação diz.
- Links externos do README.
- O texto do agente fora das afirmações com citação: ele passa só pelas verificações de voz, comentários, README e deriva.
- Imports (`@`) em arquivo de instrução escrito por pessoa: o texto importado de `docs/` chega ao agente, e a Forja não o lê.
- O efeito da instrução de voz. Instruir não faz o modelo obedecer. A medida do gate 12 mostra o que ele escreveu.
