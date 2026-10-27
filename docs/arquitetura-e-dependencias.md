# Arquitetura (gate 9)

O gate 9 olha o grafo de dependências entre **diretórios** do projeto e reprova o que a tentativa piora. Tem três checks, todos em **modo observação**: o resultado aparece no resumo, e só a política “não consegui medir” varia entre eles. Para bloquear, promova com uma decisão registrada no `forja.toml`, como descrito em [segurança e dependências](seguranca-e-dependencias.md#promover-para-bloqueio).

| Check | Reprova | Se não conseguir medir |
| --- | --- | --- |
| `dependency_cycles` | ciclo novo entre diretórios, ou ciclo antigo que ganhou um diretório | bloquear |
| `layer_rules` | aresta nova de uma camada para outra **acima** dela | bloquear |
| `package_metrics` | diretório tocado cuja distância da sequência principal passou do limite e cresceu | registrar como premissa |

Todos têm catraca: só o que a tentativa trouxe de novo reprova. Ciclo, aresta ou distância que já existiam no commit pai são o passado do repositório.

## O que é nó e o que é aresta

- **Nó** é o diretório do arquivo de produção, relativo ao projeto (a raiz é `.`). Em monorepo, cada projeto tem o seu grafo e não há aresta entre projetos. Pai e filho são nós distintos. Arquivo de teste, fixture e documentação ficam fora.
- **Aresta** é um `import` que resolve para outro diretório do mesmo projeto. Aresta de um diretório para ele mesmo não existe. O que não resolve é externo e fica fora.
- A Forja **não deduz** a arquitetura: o grafo vem só dos imports e as camadas vêm só do que você declara.

Como cada linguagem é lida:

| Linguagem | Conta como aresta | Não é visto |
| --- | --- | --- |
| Python | todo `import` e `from … import`, inclusive dentro de função e sob `TYPE_CHECKING`; relativo e absoluto; `from m import n` vira `m.n` se for módulo, senão `m` | `importlib`, `__import__` |
| Go | caminho do `import` com o prefixo do `module` do `go.mod` | `_test.go` (fora do grafo) |
| Java | `import a.b.C;`, `a.b.*;` e `import static`, contra o `package` declarado em cada arquivo | nome qualificado no corpo sem `import` |
| C# | todo `using` (namespace, `static`, alias, `global`), contra os `namespace` declarados | referência sem `using` |
| JavaScript e TypeScript | `import`, `export … from`, `import type`, `import()` e `require()` com literal **relativo** (`./`, `../`), com extensões e `index` | `paths` do `tsconfig`, aliases de bundler, especificador montado em execução |

## Ciclos

Ciclo é um componente fortemente conexo com mais de um diretório. A tentativa reprova quando algum componente do grafo novo não cabe em nenhum do antigo. A mensagem traz o caminho do ciclo e o tamanho dele.

- Ciclo antigo que continua igual ou encolhe aprova. Ciclo antigo que ganhou um diretório reprova.
- Diretório renomeado ou movido que estava num ciclo aparece como ciclo novo, porque o nome mudou.
- **Go não tem ciclo de pacote:** o compilador o recusa, então este check nunca dispara nele.
- Ciclo entre arquivos do mesmo diretório não é visto.

## Camadas

Camadas são declaradas por você no `forja.toml`, **de cima para baixo**. Uma camada pode depender de si mesma e das de baixo; depender de uma camada acima é violação.

```toml
[[architecture.layers]]
name = "cli"
paths = ["src/forja/cli"]

[[architecture.layers]]
name = "orchestrator"
paths = ["src/forja/orchestrator"]

[[architecture.layers]]
name = "core"
paths = ["src/forja/core"]
```

- `paths` são diretórios do **repositório** (em monorepo também), relativos, com `/` e sem `..`, sem barra final. Um diretório pertence à camada cujo caminho o contém; com caminhos aninhados vale o mais fundo.
- Diretório que não está em nenhuma camada é livre, dos dois lados.
- O nome da camada é único; repetido, mesmo em arquivos de configuração diferentes, recusa a configuração. As listas somam entre camadas de configuração (perfil do usuário, repositório, execução), na ordem de leitura.
- A política com camadas é congelada em `policy.json` e vale na retomada. Sem camadas, o digest da política não muda.

Reprova só a **aresta nova** que viola. Dependência que já apontava para cima antes da tentativa não reprova. `Finding.target` mostra `importador -> importado`.

**Sem camadas declaradas, `layer_rules` não executa, e a Forja diz** no resumo da preparação e no da entrega: “Camadas NÃO verificadas: sem regras em [architecture].”

## Métricas de pacote

Para cada diretório, com `Ca` os diretórios que o importam e `Ce` os que ele importa:

- `I = Ce / (Ca + Ce)` (0 se ambos são 0);
- `A = tipos abstratos / tipos`;
- `D = |A + I − 1|`, a distância da sequência principal.

Tipo abstrato: Python, classe que herda de `ABC` ou `Protocol` ou tem `@abstractmethod`; Go, `interface`; Java e C#, `interface` e classe `abstract`; TypeScript, `interface` e classe `abstract`; JavaScript puro não tem (`A = 0`).

O check reprova um diretório que a tentativa **tocou**, que tem ao menos `min_types` tipos, cujo `D` passa de `max_distance` e que é novo no grafo do commit pai ou teve o `D` aumentado. Diretório não tocado não é julgado, mesmo que o `D` dele mude porque outro passou a importá-lo. `Ca`, `Ce`, `I` e `A` são evidência, não critério.

Os limiares são por linguagem e valem, até a calibração, como palpite:

| Limiar | Padrão | Quer dizer |
| --- | --- | --- |
| `max_distance` | 0,8 | `D` acima disso é longe da sequência principal |
| `min_types` | 3 | diretório com menos tipos é ignorado |

```toml
[checks.package_metrics.thresholds.python]
max_distance = 0.7
min_types = 5
```

## Quando roda e quando não conclui

Só roda se a tentativa muda arquivo de produção de linguagem lida; senão aprova. Arquivo **mudado** que não parseia, ou projeto sem nada legível depois, dá resultado inconclusivo; arquivo não mudado que não parseia fica fora dos dois grafos. Commit pai ilegível faz todo ciclo, aresta e diretório tocado contar como novo. `go.mod` sem `module` é inconclusivo.

## Linha de base e resumo

A linha de base guarda, por projeto, o número de ciclos, o de arestas e o maior `D` (em monorepo, com o sufixo `[<projeto>]`). Entram na tabela de métricas do registro de mudança e nas evidências citáveis. A barra de progresso da interface não mostra o gate 9: com os três nomes a segunda linha passa de 120 colunas.

## Limites conhecidos

- O grafo vê só o que o `import` declara e o resolvedor acha. Em Java, `import` não usado conta (o bytecode não o veria); em Python e TypeScript, import de tipo conta.
- C# não tem ferramenta de referência por namespace; a validação foi contagem manual num repositório pequeno com build verde.
- Os limiares de `package_metrics` são palpite até a calibração (fila 6 do plano de execução).
- Mudança no grafo ou em regra de camada ainda não dispara registro de decisão (ADR).
