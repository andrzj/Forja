# Gates

Um gate é uma etapa de conferência pela qual toda tentativa de um agente passa antes de valer. Cada gate reúne uma ou mais verificações (checks). A Forja numera os gates de 1 a 14 e roda as verificações em ordem de gate. Esta página explica o que um gate faz com o resultado, lista os 14 e detalha os que não têm página própria: 1, 12, 13 e 14, mais um resumo dos gates 2, 4 e 5. Para a política de cada chave, veja `..\forja-toml.md`. Para a barra de gates da tela, veja `..\ambiente.md`. Para as opções da linha de comando, veja `..\comandos.md`.

## O que é um gate

Cada verificação devolve um de quatro resultados:

| Resultado | Significado |
| --- | --- |
| Aprovado | a verificação mediu e a tentativa está dentro do critério |
| Reprovado | o critério foi violado. A verificação diz o quê, onde e, quando há número, quanto (medido e limite). |
| Inconclusivo | a medição não pôde ser feita: a ferramenta falhou, o tempo esgotou ou o código usa uma construção que a Forja não lê |
| Não aplicável | a linguagem do projeto não oferece o que a verificação precisa. Ninguém esperava que funcionasse, e passa. |

Inconclusivo nunca conta como aprovação nem como falha do agente.

Cada verificação tem um modo e uma política de inconclusivo:

| Chave | Valores | O que decide |
| --- | --- | --- |
| `mode` | `blocking`, `observation` | se o resultado decide a tentativa (`blocking`) ou só é medido e reportado (`observation`) |
| `on_inconclusive` | `block`, `premise` | o que fazer quando a medição não pôde ser feita, em verificação bloqueante |

O efeito de cada combinação:

| Resultado | `observation` | `blocking` com `block` | `blocking` com `premise` |
| --- | --- | --- | --- |
| Aprovado ou não aplicável | passa | passa | passa |
| Reprovado | aparece no relatório, nada mais | reprova a tentativa; o motivo vai para a próxima | reprova a tentativa; o motivo vai para a próxima |
| Inconclusivo | aparece no relatório, nada mais | bloqueia a tarefa; não conta como falha do agente | segue adiante e declara a lacuna como suposição (premissa) no resumo |

Duas regras de ordem:

- As verificações rodam em ordem crescente de gate. A primeira que reprova a tentativa ou bloqueia a tarefa encerra a sequência: as seguintes não rodam. Verificações em observação nunca encerram a sequência, então as que vêm depois delas ainda rodam.
- A mensagem de reprovação nomeia onde a tentativa parou, no formato `gate <número> (<verificação>): ...`. O relatório de `forja revisao` agrupa as reprovações pelo mesmo número.

## Os 14 gates

A coluna "Modo" é o padrão da Forja. Uma verificação que bloqueia por padrão aparece como `blocking`; as demais começam em `observation`.

| Gate | Nome | Verificações | Modo padrão | Página |
| --- | --- | --- | --- | --- |
| 1 | escopo | `scope`, `freeze` | `blocking`, `blocking` | esta página |
| 2 | segredos | `secrets`, `dependency_install` | `blocking`, `blocking` | resumo nesta página; `seguranca-e-dependencias.md` |
| 3 | lint | `format`, `lint`, `types` | `blocking`, `blocking`, `observation` | `tipos.md` (`types`); `format` e `lint` em `..\forja-toml.md` |
| 4 | build | `build` | `blocking` | resumo nesta página |
| 5 | testes | `tests`, `red_green` | `blocking`, `blocking` | resumo nesta página |
| 6 | e2e | `e2e`, `test_data`, `properties` | `observation` nas três | `e2e-e-dados-de-teste.md` (`e2e`, `test_data`); `teste-de-propriedades.md` (`properties`) |
| 7 | mutação | `mutation` | `observation` | `mutacao.md` |
| 8 | métricas | `complexity`, `crap`, `pass_through`, `module_depth`, `duplication` | `complexity` em `blocking`; as demais em `observation` | `duplicacao.md` (`duplication`); as demais em `..\forja-toml.md` |
| 9 | arquitetura | `dependency_cycles`, `layer_rules`, `package_metrics` | `observation` nas três | `arquitetura-e-dependencias.md` |
| 10 | segurança | `sast`, `dependency_audit`, `new_dependency` | `observation` nas três | `seguranca-e-dependencias.md` |
| 11 | diferencial | `differential` | `observation` | `teste-diferencial.md` |
| 12 | voz | `voice`, `comments` | `observation` nas duas | esta página |
| 13 | citações e rastreabilidade | `citations`, `traceability` | `observation` nas duas | esta página |
| 14 | documentação | `change_record`, `readme`, `doc_drift`, `adr` | `observation` nas quatro | esta página |

A barra de gates da tela mostra os gates de 1 a 12. Os gates 13 e 14 rodam do mesmo modo, mas não têm marca na barra. Os nomes dos gates 13 e 14 nesta tabela são descritivos; a Forja os identifica pelo número e pelo `<id>` da verificação.

Nem toda verificação roda em toda etapa:

| Etapa | Verificações que rodam |
| --- | --- |
| especificador e arqueólogo | `scope` e `citations`; o especificador também roda `traceability` |
| autor de testes | as dos gates 1 a 12, com `red_green` no lugar de `tests` |
| implementador | as dos gates 1 a 12; `freeze` entra quando o autor de testes entregou testes |
| documentador | as dos gates 1 a 12, mais `citations`, `readme`, `adr`, `doc_drift` e `change_record` |

## Gate 1: escopo

O gate 1 confere que a tentativa mexeu só no que o papel dela permite, e não demais. Roda em toda etapa, e `scope` e `freeze` bloqueiam por padrão. Nenhuma das duas fica inconclusiva: o resultado é sempre aprovado ou reprovado.

### `scope`

`scope` reprova a tentativa por qualquer um destes motivos:

| Motivo | Quando |
| --- | --- |
| nada mudou | a tentativa não alterou arquivo algum (o especificador e o arqueólogo, que não escrevem arquivos, estão isentos) |
| arquivo que o papel não pode mudar | o implementador só muda arquivos de produção; o autor de testes só muda testes e dados de teste, e só dentro do diretório de testes; o documentador só muda documentação; o especificador e o arqueólogo não mudam arquivo nenhum |
| fora do escopo da tarefa | o implementador mexeu num arquivo que a tarefa não listou |
| arquivo ignorado pelo git | a tentativa criou um arquivo que o `.gitignore` esconde do commit mas que o build e os testes enxergam. Caches de ferramentas (`.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.hypothesis` e os `.pyc` de `__pycache__`) não contam. |
| comentário que cala uma ferramenta | linha adicionada com `noqa`, `type: ignore`, `mypy: ignore` (ou `basic`, `off`; o mesmo para `pyright:`), `pylint: disable`, `fmt: off`, `fmt: skip`, `yapf: disable`, `gitleaks:allow`, `nosec`, `nosem`, `pragma: no ...`, `lizard forgive` e `generated code` (sem diferenciar maiúsculas de minúsculas) |
| tamanho | mais arquivos ou mais linhas do que o limite |
| arquivos declarados | o agente declarou uma lista de arquivos alterados e ela difere da lista real |

Mudar a lista de dependências de um manifesto é a única exceção ao limite de papel: o implementador pode, num manifesto dentro do escopo da tarefa, e o autor de testes, em qualquer manifesto. A dependência nova é examinada pelo gate 10.

O documentador não é contado nos limites de tamanho. Dentro de `docs/mudancas`, ele só pode mudar o registro de mudança e o diário da própria tarefa.

| Chave | Padrão | Efeito |
| --- | --- | --- |
| `[checks.scope.limits] max_files` | `8` | máximo de arquivos que a tarefa pode mudar |
| `[checks.scope.limits] max_lines` | `400` | máximo de linhas mudadas |

A Forja aplica o menor valor entre o limite da tarefa e o da política, então a política só pode apertar o limite.

### `freeze`

`freeze` protege os testes que o autor de testes entregou. Ele guarda uma identificação (resumo de conteúdo) de tudo o que está sob o diretório de testes e dos arquivos que a linguagem classifica como teste ou dado de teste. Se o implementador muda, move ou apaga qualquer um, a tentativa reprova e cada arquivo tocado vira um achado. Fim de linha de arquivo de teste em código não conta como mudança. Numa etapa extra de testes, o `freeze` vira uma regra mais frouxa: pode adicionar arquivos de teste, mas não mudar, mover nem apagar um que já existe.

O diretório de testes vem de `[tests] root`. Num repositório que é um só projeto Python o padrão é `tests`. Nas demais linguagens não há padrão, e os testes que ficam junto do código entram pela classificação da linguagem.

```toml
# Tarefas menores do que o padrão da Forja.
[checks.scope.limits]
max_files = 5
max_lines = 200

# Os testes deste repositório ficam em src/test, não em tests.
[tests]
root = "src/test"
```

O primeiro bloco aperta o orçamento da tarefa para 5 arquivos e 200 linhas. O segundo diz onde o agente de testes escreve e onde o `freeze` olha.

## Gate 2: segredos, resumo

O detalhe está em `seguranca-e-dependencias.md`.

| Verificação | O que faz |
| --- | --- |
| `secrets` | roda o gitleaks sobre as linhas que a tentativa acrescentou. Remover um segredo nunca reprova. O achado nomeia a regra e o lugar e nunca copia o segredo. Se o gitleaks não termina, ou termina com um código que não é o de achado, o resultado é inconclusivo. |
| `dependency_install` | prova que cada dependência nova existe no registro e a instala antes de qualquer execução, para que o build e os testes rodem no ambiente que a tentativa declarou. Só o registro do Python (PyPI) tem instalador. Um nome que o registro não lista, ou uma instalação que falha, reprova a tentativa. Idade e uso da dependência são julgados no gate 10. |

As duas bloqueiam por padrão, com `on_inconclusive = "block"`. Nenhuma tem chave além de `mode` e `on_inconclusive`.

## Gates 4 e 5: build e testes, resumo

Os dois rodam uma vez por linguagem do projeto, e o que encontram se soma.

| Verificação | Gate | O que faz |
| --- | --- | --- |
| `build` | 4 | roda o build. Reprova com `the file does not compile` para erro de compilação em um arquivo, ou `the build failed`. |
| `tests` | 5 | roda os testes. Reprova cada teste com resultado `failed` ou `error`, e também o teste que passava na base e agora sumiu, foi pulado ou não passou. Testes que a base já mostrou instáveis ficam em quarentena e não reprovam. |
| `red_green` | 5 | roda no lugar de `tests` na etapa do autor de testes. Cada critério precisa ter um teste declarado, cada teste declarado precisa existir, ser um arquivo de teste e falhar no código com o defeito. Teste que dá erro de importação ou de coleta não conta como falha pelo defeito. Nenhum outro teste pode falhar, e os que passavam na base têm de continuar passando. |

As três bloqueiam por padrão, com `on_inconclusive = "block"`. Numa etapa extra de testes, que descreve código que já existe, vale `tests`, e os testes têm de passar.

| Chave | Efeito |
| --- | --- |
| `[checks.build.commands] build` | comando de build do repositório no lugar do da linguagem |
| `[checks.tests.commands] test` | comando de testes do repositório |
| `[checks.red_green.commands] test` | comando de testes do repositório para a etapa do autor de testes |

```toml
# O repositório compila por um alvo próprio.
[checks.build.commands]
build = ["make", "build"]

# Os testes rodam com pytest e param no primeiro erro, nas duas verificações que usam o comando de teste.
[checks.tests.commands]
test = ["python", "-m", "pytest", "-q", "-x"]

[checks.red_green.commands]
test = ["python", "-m", "pytest", "-q", "-x"]

# Se os testes não puderem rodar, a tarefa segue e a lacuna vira premissa no resumo.
[checks.tests]
on_inconclusive = "premise"
```

O comando é uma lista (programa e argumentos), nunca um texto de shell. Mais sobre comandos em `..\forja-toml.md`.

## Gate 12: voz

O gate 12 mede se o texto que a tentativa acrescenta soa como escrito no piloto automático. As duas verificações começam em `observation` com `on_inconclusive = "premise"` e nunca aceitam `mode = "blocking"`: a Forja instrui o agente e reporta o que mediu, sem reprovar a tentativa. Um `mode = "blocking"` nelas é erro de política.

### `voice`

`voice` olha a prosa que a tentativa acrescenta: as linhas novas de arquivos de documentação, os comentários novos de arquivos de código de uma linguagem que a Forja lê (Python, Go, Java, C#, JavaScript e TypeScript) e a mensagem de commit. Uma string no código é dado, não prosa, e fica de fora. O achado diz o arquivo, a linha e por que o padrão está na lista, e nunca copia o texto.

Os marcadores da Forja:

| Identificador | O que marca |
| --- | --- |
| `greeting` | abertura que cumprimenta em vez de dizer algo (`claro,`, `certamente.`, `sure,`) |
| `self-reference` | o modelo falando de si (`como uma IA`, `as a language model`) |
| `inflated` | vocabulário que infla e não diz nada (`divisor de águas`, `no cenário atual`, `paradigm shift`) |
| `announcement` | frase que anuncia que algo importa em vez de dizê-lo (`é importante ressaltar que`) |
| `offer` | oferta de mais ajuda (`espero que isso ajude`, `fico à disposição`) |
| `emoji` | emoji em texto que se lê como documentação |

Além dos marcadores, `voice` conta os travessões longos (o caractere Unicode U+2014) que o texto acrescentado de um arquivo, ou a mensagem de commit, traz. Acima do limite, o achado é reportado. Só o travessão longo conta. O agente é instruído a não usar nenhum.

| Chave | Tipo | Padrão | Efeito |
| --- | --- | --- | --- |
| `[checks.voice.limits] max_dashes` | inteiro | `3` | travessões longos que um arquivo pode acrescentar antes do achado |
| `[voice] markers_off` | lista de identificadores | vazia | marcadores da Forja que o repositório desliga. Identificador que a Forja não tem é ignorado. |
| `[voice] markers_extra` | lista de expressões regulares | vazia | padrões proibidos a mais, em sintaxe do Python (`re`), sem diferenciar maiúsculas de minúsculas. Não podem casar o texto vazio. Cada um vira o marcador `repository-N`, com N a posição na lista a partir de 1. |

A instrução ao agente reflete o que o repositório ligou e desligou.

### `comments`

`comments` aplica duas regras de comentário a código novo, e nunca culpa código antigo. Não tem chave de política além de `mode` e `on_inconclusive`; os dois números abaixo são fixos.

| Achado | Quando |
| --- | --- |
| `a comment repeats the code next to it` | um comentário novo repete o código ao lado: tem ao menos 2 palavras com significado e 75% ou mais delas já estão na linha que ele comenta (identificadores são separados em `camelCase` e `snake_case`, e palavras de uma ou duas letras e palavras vazias como `the` e `para` são ignoradas) |
| `the new public <tipo> <nome> has no comment` | um símbolo público que a tentativa criou, num arquivo de produção, sem comentário logo acima (ou sem docstring, em Python). Símbolo que já existia no arquivo antes não conta. |

Público é o que cada linguagem declara: em Python, nome sem sublinhado inicial; em Go, nome com inicial maiúscula; em Java e C#, o marcado como `public`; em JavaScript e TypeScript, o exportado.

```toml
[voice]
# Este repositório usa emoji na documentação.
markers_off = ["emoji"]
# Proíbe a palavra "sinergia" na prosa nova. A aspa simples evita a barra invertida dupla.
markers_extra = ['\bsinergia\b']

# Nenhum travessão longo tolerado.
[checks.voice.limits]
max_dashes = 0
```

O primeiro bloco desliga o marcador `emoji` e acrescenta um padrão próprio, que aparece nos achados como `repository-1`. O segundo troca o limite de 3 travessões por zero.

## Gate 13: citações e rastreabilidade

O gate 13 confere que o que um agente afirma tem origem. As duas verificações começam em `observation` com `on_inconclusive = "block"`. Nenhuma tem chave de política além de `mode` e `on_inconclusive`.

### `citations`

Uma afirmação (claim) é uma frase com ao menos uma citação. `citations` confere cada citação contra o repositório:

| Citação | O que é conferido | Achado |
| --- | --- | --- |
| de arquivo | o arquivo existe no repositório, é legível como texto e tem as linhas citadas | `<arquivo> is not a file of the repository`, `<arquivo> cannot be read as text` ou `<arquivo>:<ini>-<fim> is past the end of the file` |
| de evidência | existe uma medição ou um gate com esse nome | `no measurement or gate called '<nome>'` |
| de fato | o fato está no arquivo de fatos que o dono forneceu | `no recorded fact '<id>'` |

Cada achado diz de qual afirmação vem (`claim <número>`). O gate confere que a citação existe e cabe no arquivo, não que o trecho sustenta a afirmação: isso é da revisão. Roda no especificador e no arqueólogo, no documentador e em qualquer papel que declare afirmações. As instruções do implementador e do autor de testes não pedem afirmações, e o gate só olha o que eles declararem.

### `traceability`

`traceability` roda só no especificador. A entrada é cortada em elementos com id (`E1`, `E2` e assim por diante), e cada elemento tem de virar um critério ou ser declarado como deixado de fora, com motivo. O gate reprova:

| Achado | Quando |
| --- | --- |
| `criterion <n> comes from <id>, which is not in the input` | um critério aponta para um elemento que a entrada não tem |
| `<id> is left out but is not in the input` | um elemento deixado de fora que não existe |
| `<id> has no criterion and is not left out` | um elemento que nenhum critério cobre e que não foi deixado de fora |

O elemento deixado de fora com motivo não reprova: o motivo vira premissa no resumo. Que o critério diga o que o elemento diz é da revisão. Prosa corrida vira poucos elementos grandes e a rastreabilidade fica grossa.

```toml
# Em observação, esta política fica guardada: só tem efeito no dia em que
# a verificação for promovida a bloqueante.
[checks.citations]
on_inconclusive = "premise"

# Torna a rastreabilidade bloqueante. Nasce em observação, então a promoção
# precisa de data e motivo.
[checks.traceability]
mode = "blocking"
promotion = { date = 2030-01-31, reason = "os critérios do especificador passaram a ter origem em todas as execuções revisadas" }
```

## Gate 14: documentação

O gate 14 roda na etapa do documentador. As quatro verificações começam em `observation`; `change_record` com `on_inconclusive = "block"` e as outras três com `"premise"`. Nenhuma tem chave de política além de `mode` e `on_inconclusive`.

### `change_record`

A Forja escreve o registro de mudança da tarefa em `docs/mudancas/<tarefa>.md` com os fatos que ela mediu. O gate não confia cegamente nesse arquivo. Reprova quando:

| Achado | Quando |
| --- | --- |
| `the change record is missing` | o arquivo não existe ou não é legível |
| `the change record lacks the section '<seção>'` | falta uma das seções: `## Arquivos`, `## Símbolos`, `## Métricas`, `## Gates aprovados`, `## Ferramentas`, `## Premissas`, `## Para reverter` e `## Porquê e impacto` |
| `the files and symbols in the change record differ from the task's changes` | as seções de arquivos e símbolos não são as que o diff da tarefa produz agora |
| `the change record has no reason or impact with a citation` | `## Porquê e impacto` está vazia ou diz `Nenhum.` |

O símbolo removido vem com a prova de que nenhum outro arquivo o menciona, ou com a lista dos arquivos que ainda o mencionam, e um símbolo público removido é marcado.

### `readme`

`readme` julga o `README.md` (ou `README.rst`) da raiz sem usar modelo de linguagem. Reprova quando:

| Achado | Quando |
| --- | --- |
| `there is no README` | não há README na raiz, ou ele é um link |
| `the README has no section for <tema>` | falta um tema. Os seis são: o que é o projeto (o corpo de abertura, sob o título, também vale), como construir, como testar, como rodar, como configurar e dependências. Um tema é atendido por um título que o nomeia, em português ou inglês. |
| `the <build ou test> section cites no command` ou `... cites <x>; the project runs <y>` | a seção de construir ou a de testar não traz comando em bloco de código, ou traz comando que o projeto não roda. Compara-se o programa e, quando há, o subcomando: `pytest -q` e `python -m pytest` são o mesmo `pytest`; `go build ./...` é `go build`. |
| `the link to <caminho> points at nothing` | link relativo para arquivo que não existe, ou para âncora (`#titulo`) sem título correspondente |

O documentador só pode mudar as seções que tinham problema. Uma seção que estava boa e foi alterada gera `the README section '<título>' had no problem and changed`.

### `doc_drift`

`doc_drift` procura, na documentação do repositório, citações a coisas que não existem mais. Lê o que está entre crases, fora de blocos de código, e confere:

| Citação | Conferência |
| --- | --- |
| caminho (`src/app/x.py`, `config.toml`, com ou sem `:linha`) | o arquivo ou diretório existe, a partir da raiz ou da pasta do documento |
| `make <alvo>` | o `Makefile` declara o alvo |
| `npm run <script>` (também `yarn`, `pnpm`, `bun`) | o `package.json` declara o script |
| símbolo (nome que parece código: com `()`, sublinhado, ponto ou maiúsculas e minúsculas misturadas) | cada parte do nome aparece como palavra em algum arquivo que não é documentação |

Só a deriva nova reprova. Uma citação que o documento já tinha na base da tarefa, apontando para algo que já não existia, é deixada. Uma afirmação recém-escrita, ou um nome que a tarefa removeu, reprova. Os registros em `docs/mudancas` são histórico, não afirmações, e não são lidos.

### `adr`

`adr` cobra um registro de decisão quando a tarefa traz algo que pede uma. Duas regras detectam:

- uma dependência externa nova em um manifesto;
- um módulo novo: um diretório com um arquivo de produção que a tarefa acrescentou e que não tinha nenhum na base.

Com um detector acionado, a tarefa precisa de um registro novo e numerado em `docs/adr` (`NNNN-titulo.md`, com ao menos quatro dígitos) que tenha um título de seção sobre as alternativas e outro sobre as consequências (ou trade-offs). O número não pode estar em uso. Um registro bom basta. Um registro que ninguém pediu não reprova. A Forja diz ao documentador o próximo número livre.

```toml
# Torna o registro de mudança bloqueante. Se ele não puder ser conferido, a tarefa para.
[checks.change_record]
mode = "blocking"
on_inconclusive = "block"
promotion = { date = 2030-01-31, reason = "todo registro de mudança passou a trazer as oito seções" }

# Só reporta a deriva de documentos; o padrão já é esse, então a linha é opcional.
[checks.doc_drift]
mode = "observation"
```

O primeiro bloco promove `change_record` a bloqueante, o que exige `promotion` com data e motivo. O segundo repete o padrão de `doc_drift`, que não precisa de `promotion` porque ela já nasce em observação.

## Mudar o modo de um gate

O modo é por verificação, não por gate: para mudar um gate inteiro, mude cada verificação dele. Promover uma verificação de `observation` para `blocking` exige `promotion` com `date` e `reason`. Afrouxar uma que bloqueia por padrão não exige. `voice` e `comments` nunca viram bloqueantes. O passo a passo, com exemplos, está em `seguranca-e-dependencias.md#promover-para-bloqueio`, e a regra completa, em `..\forja-toml.md`.
