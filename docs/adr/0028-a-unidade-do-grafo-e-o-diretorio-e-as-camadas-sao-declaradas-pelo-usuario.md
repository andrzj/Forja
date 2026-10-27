# 0028. A unidade do grafo é o diretório e as camadas são declaradas pelo usuário

## Contexto

A Especificação manda que o gate 9 reprove ciclo de dependência novo, violação de regra de camada e piora nas métricas de pacote, e que as ferramentas próprias sejam validadas contra uma de referência. Não diz qual é o nó do grafo, onde se declaram as camadas nem como se mede a abstração em cada linguagem.

## Decisão

- **Nó = diretório do arquivo de produção.** Em Go o diretório é o pacote; em Java e C# o pacote ou namespace segue o diretório por convenção; em Python é o pacote; em JavaScript e TypeScript é a pasta. Nessas linguagens, a referência a outro arquivo do mesmo pacote não passa por `import`, então um grafo por arquivo ficaria incompleto. Em monorepo, um grafo por projeto, sem aresta entre projetos.
- **Aresta = `import` que resolve para outro diretório do mesmo projeto.** Os leitores são por dialeto (`imports(root)`), os resolvedores por linguagem em `checks\architecture\`. Alias de TypeScript não é resolvido; o que não resolve é externo.
- **As camadas são declaradas pelo usuário em `[architecture]` e a Forja nunca as deduz.** A ordem é de cima para baixo; aresta para camada acima é violação; diretório fora de toda camada é livre. Sem camadas, `layer_rules` não executa e o resumo diz “Camadas NÃO verificadas” (mesmo tratamento do SAST sem regras, ADR 0024).
- **Catraca.** Reprova ciclo ou componente que não cabe em nenhum do estado antigo, aresta nova para camada acima, e diretório tocado cujo `D` passou do limite e cresceu. O passado do repositório não reprova.
- **Observação.** Os três checks nascem em observação; “não consegui medir” bloqueia em ciclos e camadas e vira premissa nas métricas, cujos limiares (`max_distance` 0,8, `min_types` 3) são palpite até a calibração.
- **Validação (regra da Especificação).** Python contra o `grimp` (mesmas 134 arestas na própria Forja), Go contra `go list`, Java contra `jdeps`, TypeScript contra `dependency-cruiser`; C# por contagem manual com build verde. As divergências viraram limites declarados em `docs/arquitetura-e-dependencias.md`.

## Alternativas

- *Nó = arquivo.* Mais fino, mas não vê ciclo entre pacotes quando a referência é implícita (Go, Java, C#) e dá milhares de nós onde a revisão pensa em módulos.
- *Deduzir as camadas das métricas ou da estrutura de pastas.* O modelo de linguagem ou a heurística decidiria o que é arquitetura; a regra é do dono do repositório, não de quem a mede.
- *Reprovar toda violação existente.* Contraria a catraca: faxina não é tarefa de refatoração incremental.
- *Resolver `paths` do `tsconfig` e aliases.* Dependeria de rodar o bundler; fica como limite.

## Consequências

O gate só vale em camadas quando o usuário as escreve; sem elas, ciclos e métricas continuam sendo medidos. O grafo da Forja tem menos arestas que a referência quando há alias de TypeScript ou `import` morto em Java, e não vê ciclo entre arquivos do mesmo diretório. Diretório renomeado que estava num ciclo antigo reaparece como ciclo novo. O uso está em `docs/arquitetura-e-dependencias.md`; o plano, em `docs/plano-gate-9.md`.
