# Gate 9: arquitetura e dependências

O gate 9 olha o grafo de dependências entre **diretórios** do projeto e reprova o que a tentativa piora. Tem três verificações: `dependency_cycles`, `layer_rules` e `package_metrics`. As três começam em **observação**: o resultado aparece no relatório e nunca bloqueia a tentativa. Para bloquear, promova com uma decisão registrada no `forja.toml`, como descrito em [promover para bloqueio](seguranca-e-dependencias.md#promover-para-bloqueio). A sintaxe geral do arquivo está em [forja-toml](..\forja-toml.md), e o índice dos gates em [README](README.md).

| Verificação | Reprova | Modo padrão | Se não conseguir medir |
| --- | --- | --- | --- |
| `dependency_cycles` | ciclo novo entre diretórios, ou ciclo antigo que ganhou um diretório | `observation` | `block` |
| `layer_rules` | dependência nova de uma camada para outra **acima** dela | `observation` | `block` |
| `package_metrics` | diretório tocado que ficou longe da sequência principal e piorou | `observation` | `premise` |

A coluna "Se não conseguir medir" é o `on_inconclusive` padrão. Ele só tem efeito depois da promoção; em observação, um resultado inconclusivo aparece no relatório e mais nada. Veja "Modo e política de inconclusivo" em [forja-toml](..\forja-toml.md).

As três têm catraca: só o que a tentativa trouxe de novo reprova. Ciclo, dependência ou distância que já existiam antes da tentativa são o passado do repositório e não contam.

## O que é nó e o que é aresta

- **Nó** é o diretório de um arquivo de produção, relativo ao projeto (a raiz do projeto é `.`). Pai e filho são nós distintos. Arquivo de teste, fixture e documentação ficam fora do grafo.
- **Aresta** é um `import` (ou equivalente) em um arquivo de um diretório que aponta para um arquivo ou pacote de outro diretório do mesmo projeto. Aresta de um diretório para ele mesmo não existe. O que não resolve para o projeto é externo e fica fora.
- Em monorepo, cada projeto tem o seu grafo e não há aresta entre projetos.
- A Forja **não deduz** a arquitetura: o grafo vem só dos imports, e as camadas vêm só do que você declara.

### Como cada linguagem é lida

| Linguagem | Conta como aresta | Não é visto |
| --- | --- | --- |
| Python | todo `import` e `from ... import`, em qualquer ponto do arquivo (inclusive dentro de função e sob `TYPE_CHECKING`), relativo ou absoluto. `from m import n` vira `m.n` se for módulo do projeto, senão `m` | `importlib` e `__import__`; pacote sem `__init__.py` (o nome do módulo não inclui o diretório, então `import a.b` não encontra `a/b.py`) |
| Go | caminho do `import` que começa com o `module` do `go.mod` e aponta para um diretório com código de produção | arquivos `_test.go` |
| Java | `import a.b.C;`, `import a.b.*;` e `import static`, casados com o `package` e os tipos declarados em cada arquivo | nome qualificado no corpo sem `import`; arquivo sem `package` como destino de import |
| C# | todo `using` (de namespace, `static`, alias e `global`), casado com os `namespace` declarados | tipo usado sem `using` |
| JavaScript e TypeScript | `import`, `export ... from`, `import type`, `import()` e `require()` com texto literal **relativo** (`./` ou `../`), com ou sem extensão, e pasta com `index` | `paths` do `tsconfig`, aliases de bundler, especificador montado em execução |

Os arquivos lidos são os de extensão `.py` e `.pyi`, `.go`, `.java`, `.cs`, `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.mts`, `.cts` e `.tsx`. A leitura conta o que o `import` declara, mesmo que o nome não seja usado depois: em Java um `import` sem uso é aresta, e em Python e TypeScript um import só de tipo também é.

## `dependency_cycles`

Mede ciclos de dependência entre diretórios. Ciclo é um grupo de mais de um diretório que se importam, direta ou indiretamente.

| Aspecto | Valor |
| --- | --- |
| Linguagens | Python, Java, C#, JavaScript e TypeScript. Em Go nunca dispara: o compilador já recusa ciclo entre pacotes |
| Modo padrão | `observation` |
| `on_inconclusive` padrão | `block` |
| Chaves de política | nenhuma além de `mode`, `on_inconclusive` e `promotion` |

Reprova quando algum ciclo do código novo não cabe inteiro em nenhum ciclo do código antigo. Na prática:

- Ciclo novo reprova.
- Ciclo antigo que ganhou um diretório reprova.
- Ciclo antigo que continua igual ou encolhe aprova.
- Diretório renomeado ou movido que estava num ciclo aparece como ciclo novo, porque o nome mudou.
- Ciclo entre arquivos do mesmo diretório não é visto.

O achado diz `new dependency cycle between directories` (ou `a dependency cycle took in more directories`), traz o caminho do ciclo em `target`, com o primeiro diretório repetido no fim, e o número de diretórios no ciclo em `measured`.

Exemplo: o diretório `pedidos` passa a importar `clientes`, que já importava `pedidos`. Antes não havia ciclo.

```text
new dependency cycle between directories   pedidos -> clientes -> pedidos
```

## `layer_rules`

Mede se um diretório passou a depender de uma camada acima da sua. As camadas são as que você declara em `[architecture]`.

| Aspecto | Valor |
| --- | --- |
| Linguagens | Python, Go, Java, C#, JavaScript e TypeScript |
| Modo padrão | `observation` |
| `on_inconclusive` padrão | `block` |
| Chaves de política | nenhuma além de `mode`, `on_inconclusive` e `promotion`; as camadas ficam em `[architecture]` |

**Sem camadas declaradas, a verificação não executa**, e a Forja avisa no resumo da preparação e no da entrega: `Camadas NÃO verificadas: sem regras em [architecture].`

Reprova só a **aresta nova** que viola: um diretório de uma camada que passa a importar um diretório de uma camada acima. Dependência que já apontava para cima antes da tentativa não reprova. A mensagem é `layer <baixa> depends on <alta>, a layer above it`, e `target` mostra `importador -> importado`.

### `[architecture]`: as camadas

Declare as camadas **de cima para baixo**. Uma camada pode depender de si mesma e das que estão abaixo dela; depender de uma camada acima é violação.

| Chave | Tipo | Padrão | Efeito |
| --- | --- | --- | --- |
| `layers` | lista de tabelas `{ name, paths }` | vazia | camadas, da mais alta para a mais baixa. A ordem da lista é a ordem das camadas |
| `layers[].name` | texto não vazio | obrigatório | nome da camada. Espaços nas pontas são removidos. Único no arquivo |
| `layers[].paths` | lista de textos, não vazia | obrigatório | diretórios da camada |

Regras de `paths`:

- Caminhos **do repositório**, relativos e com `/`, mesmo em monorepo. Não podem ter `\`, `..`, `.`, barra no início ou no fim, nem unidade de disco. Por isso a raiz do repositório não pode ser uma camada; declare os diretórios dela.
- Um diretório pertence à camada cujo caminho o contém, ele mesmo ou um ancestral. Com caminhos aninhados em camadas diferentes, vale o mais longo. Em empate exato, vale a camada declarada primeiro.
- Um diretório que não está em nenhuma camada é livre, dos dois lados: não gera violação como importador nem como importado.
- Em monorepo, o diretório de um projeto é lido como o caminho do projeto mais o caminho dentro dele. Escreva o caminho completo a partir da raiz do repositório.

Nome repetido recusa o `forja.toml`, com `architecture.layers: the layer name '<nome>' is used twice`. Chave desconhecida em `[architecture]` ou em uma camada dá `unknown key`. A lista de camadas entra na política congelada na confirmação: mudar uma camada entre pausar e retomar recusa a retomada, como qualquer outra mudança de política.

Formas aceitas, todas equivalentes para a Forja.

Tabelas repetidas, a forma mais legível:

```toml
# Da camada mais alta para a mais baixa. A interface pode usar o domínio
# e a infraestrutura; o domínio pode usar a infraestrutura; a infraestrutura
# não pode importar nenhuma das duas.
[[architecture.layers]]
name = "interface"
paths = ["src/app/cli"]

[[architecture.layers]]
name = "dominio"
paths = ["src/app/dominio"]

[[architecture.layers]]
name = "infra"
paths = ["src/app/infra"]
```

Lista numa única chave, com mais de um diretório por camada:

```toml
[architecture]
layers = [
  { name = "interface", paths = ["src/app/cli", "src/app/web"] },  # dois diretórios na mesma camada
  { name = "dominio",   paths = ["src/app/dominio"] },
  { name = "infra",     paths = ["src/app/infra"] },
]
```

Caminhos aninhados: o diretório mais específico vence.

```toml
[[architecture.layers]]
name = "dominio"
paths = ["src/app/dominio"]

[[architecture.layers]]
name = "adaptadores"
paths = ["src/app/dominio/adaptadores"]   # fica na camada "adaptadores", não em "dominio"
```

Monorepo: os caminhos partem da raiz do repositório, não do projeto.

```toml
# O projeto em servicos/pedidos tem as camadas web, servico e repositorio.
[[architecture.layers]]
name = "web"
paths = ["servicos/pedidos/src/web"]

[[architecture.layers]]
name = "servico"
paths = ["servicos/pedidos/src/servico"]

[[architecture.layers]]
name = "repositorio"
paths = ["servicos/pedidos/src/repositorio"]
```

## `package_metrics`

Mede a distância de cada diretório tocado até a sequência principal das métricas de Martin. Para cada diretório, com `Ca` os diretórios que o importam e `Ce` os que ele importa:

- `I = Ce / (Ca + Ce)`, a instabilidade (0 se ambos são 0);
- `A = tipos abstratos / tipos`, a abstração (0 se não há tipos);
- `D = |A + I - 1|`, a distância da sequência principal.

Um diretório bem posicionado é estável e abstrato, ou instável e concreto. `D` perto de 0 é bom; perto de 1 é o pior caso (estável e concreto, ou instável e abstrato).

| Aspecto | Valor |
| --- | --- |
| Linguagens | Python, Go, Java, C#, JavaScript e TypeScript |
| Modo padrão | `observation` |
| `on_inconclusive` padrão | `premise` |
| Chaves de política | `thresholds.<linguagem>.max_distance` e `thresholds.<linguagem>.min_types` |

O que conta como tipo abstrato:

| Linguagem | Tipo abstrato | Tipo (total) |
| --- | --- | --- |
| Python | classe que herda de `ABC` ou `Protocol`, ou tem método com `abstractmethod` | toda `class` |
| Go | `interface` | todo `type` declarado |
| Java | `interface`, `@interface` e classe `abstract` | `class`, `interface`, `enum`, `record` e `@interface` |
| C# | `interface` e classe `abstract` | `class`, `struct`, `record`, `interface` e `enum` |
| TypeScript | `interface` e classe `abstract` | `class`, `abstract class`, `interface` e `enum` |
| JavaScript | nenhum (`A = 0`) | `class` |

### Limiares

Os limiares são por linguagem. Os valores abaixo são iniciais e ainda não foram calibrados com dados de execuções reais.

| Chave | Padrão | Valor lido | Efeito |
| --- | --- | --- | --- |
| `max_distance` | `0.8` | número maior que zero | `D` acima disso é longe da sequência principal |
| `min_types` | `3` | número maior que zero | diretório com menos tipos que isso é ignorado |

Um valor zero ou negativo não dá erro: a Forja usa o padrão no lugar. Nome inexistente, linguagem desconhecida ou valor que não é número dão erro. Uma linguagem sem valor no arquivo usa o padrão.

### Quando reprova

O diretório precisa cumprir tudo isto:

1. foi **tocado** pela tentativa (tem arquivo de produção adicionado, alterado ou renomeado);
2. tem ao menos `min_types` tipos;
3. tem `D` acima de `max_distance`;
4. é novo no grafo anterior, ou o `D` dele aumentou.

Diretório não tocado não é julgado, mesmo que o `D` dele mude porque outro passou a importá-lo. `Ca`, `Ce`, `I` e `A` são evidência, não critério. O achado diz `package is far from the main sequence`, com o diretório em `target`, o `D` arredondado em `measured` e o limite em `limit`.

```toml
# Python mais rígido: distância máxima de 0.7, e só diretórios com 5 tipos ou mais entram.
[checks.package_metrics.thresholds.python]
max_distance = 0.7
min_types = 5

# Go com o padrão de distância, mas olhando diretórios pequenos.
[checks.package_metrics.thresholds.go]
min_types = 2
```

## Quando a verificação roda e quando não conclui

As três verificações só rodam se a tentativa muda arquivo de produção de uma linguagem lida; senão aprovam. Um projeto que a tentativa não tocou não é lido. Só remoção de arquivo também aprova, porque não sobra arquivo tocado.

Resultado inconclusivo (a verificação não consegue medir) quando:

| Situação | Detalhe |
| --- | --- |
| arquivo **mudado** que não parseia | `<arquivo> does not parse, so its imports cannot be read` |
| nenhum arquivo do projeto pôde ser lido | `no file of the project could be read` |
| Go com `go.mod` sem `module` | `go.mod names no module` |

Arquivo **não mudado** que não parseia fica fora dos dois grafos. Se o código anterior à tentativa não puder ser lido, todo ciclo, dependência e diretório tocado conta como novo.

O que acontece com um inconclusivo depende do modo: em observação aparece no relatório; se promovida, `on_inconclusive = "block"` bloqueia a tarefa sem contar como falha do agente, e `"premise"` segue adiante e declara a lacuna como suposição.

## O que acontece ao falhar

| Modo | Efeito de uma reprovação |
| --- | --- |
| `observation` (padrão) | o achado aparece no relatório; a tentativa segue |
| `blocking` | a tentativa é reprovada e o achado (mensagem, alvo, valor e limite) vai para o agente na próxima tentativa |

A linha de base guarda, por projeto, o número de ciclos, o de dependências entre diretórios e o maior `D` (em monorepo, com o sufixo `[<projeto>]`). Esses números entram na tabela de métricas do registro de mudança. A barra de gates da interface mostra o gate 9 como `arquitetura`, somando as três verificações: ele falha se qualquer uma falha.

## Promover para bloqueio

Promover é mudar `mode` de `observation` para `blocking`. Isso exige `promotion` com `date` e `reason`; sem ela, a Forja recusa o `forja.toml`. As regras completas estão em [promover para bloqueio](seguranca-e-dependencias.md#promover-para-bloqueio) e em "Promoção" na página [forja-toml](..\forja-toml.md).

```toml
# Ciclo novo entre diretórios passa a reprovar a tentativa.
# Se o grafo não puder ser lido, a tarefa é bloqueada (padrão: block).
[checks.dependency_cycles]
mode = "blocking"
promotion = { date = 2030-02-15, reason = "o repositório está sem ciclos entre diretórios" }

# Violação de camada passa a reprovar. Só faz efeito com [architecture] declarado.
[checks.layer_rules]
mode = "blocking"
promotion = { date = 2030-02-15, reason = "as camadas de [architecture] refletem o desenho atual" }

# Métricas de pacote bloqueantes, mas sem parar a tarefa quando não for possível medir:
# a lacuna segue como suposição declarada.
[checks.package_metrics]
mode = "blocking"
on_inconclusive = "premise"
promotion = { date = 2030-02-15, reason = "os limiares foram ajustados aos dados do repositório" }
```

Promover `layer_rules` sem declarar camadas não bloqueia nada: sem `[architecture]` a verificação não executa.

## Exemplo completo

Um repositório Python com três camadas, limiares próprios para as métricas e ciclos bloqueando:

```toml
# Camadas, da mais alta para a mais baixa.
[[architecture.layers]]
name = "cli"
paths = ["src/loja/cli"]

[[architecture.layers]]
name = "servicos"
paths = ["src/loja/servicos"]

[[architecture.layers]]
name = "nucleo"
paths = ["src/loja/nucleo"]

# Ciclo novo entre diretórios passa a bloquear.
[checks.dependency_cycles]
mode = "blocking"
promotion = { date = 2030-02-15, reason = "o repositório está sem ciclos entre diretórios" }

# As violações de camada continuam só no relatório (observação, o padrão).
# Métricas de pacote: um pouco mais rígido que o padrão para Python.
[checks.package_metrics.thresholds.python]
max_distance = 0.7
min_types = 4
```

## Limites conhecidos

- O grafo vê só o que o `import` declara e o resolvedor encontra. O que a tabela "Como cada linguagem é lida" lista como não visto fica fora.
- Dependência entre arquivos do mesmo diretório não é aresta, por isso ciclo e camada só enxergam relações entre diretórios.
- Os limiares de `package_metrics` são valores iniciais, ainda sem calibração.
- Mudança no grafo ou em regra de camada não gera, por si só, pedido de registro de decisão no gate 14.
- A leitura de C# foi conferida por contagem manual, sem ferramenta de referência por namespace.
