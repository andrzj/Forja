# Teste de propriedades: instrução ao agente e o check `properties`

A Forja pede ao autor de testes que escreva teste de propriedades quando o código se presta a isso, e mede se a tentativa que muda código de produção trouxe algum (ADR 0040). É instrução e observação: nada aqui bloqueia a tentativa.

## O que é

Um teste de propriedades afirma uma regra que vale para qualquer entrada e deixa uma biblioteca tentar muitas entradas. É um teste comum do executor de cada linguagem, sem executor próprio, e roda sob os gates que já medem testes.

## Uma biblioteca por linguagem

| Linguagem | Biblioteca | Como o agente a usa |
| --- | --- | --- |
| Python | Hypothesis | `@given(...)` num teste do pytest |
| TypeScript | fast-check com `@fast-check/vitest` | `test.prop([fc.integer()])("regra", ...)` |
| Java | QuickTheories | `qt().forAll(...).check(...)` num teste JUnit |
| Go | `pgregory.net/rapid` | `rapid.Check(t, func(t *rapid.T) { ... })` |
| C# | FsCheck com `FsCheck.Xunit` | `[Property]` num método |

São dependências de teste do repositório, não ferramentas da Forja: entram pelo mecanismo das dependências do agente (ADR 0036) e nada vai ao manifesto de ferramentas.

## O que o agente lê

Só o autor de testes recebe a seção `## Property tests` do pacote, com as bibliotecas das linguagens detectadas no repositório. O texto é fixo (`orchestrator\properties_brief.py`, `VERSION`) e diz quando escrever uma propriedade: função pura cujo resultado segue uma regra, par que se desfaz (codificar e decodificar), invariante, função com uma versão mais simples e lenta para comparar. Linguagem sem biblioteca da Forja não recebe instrução.

## Semente

Teste aleatório sem semente fixa quebra a repetição que a Forja faz (linha de base, cabeça, mutação). A Forja fixa a semente onde a ferramenta permite sem editar o teste:

- **Python:** `--hypothesis-seed`, só quando `pyproject.toml` ou `requirements*.txt` da raiz declara `hypothesis` (a opção é do plugin e daria erro de uso sem ele).
- **Go:** as variáveis `RAPID_SEED` e `RAPID_NOFAILFILE=true`.
- **TypeScript, Java e C#:** a Forja não injeta nada. A instrução manda fixar a semente no próprio teste: `seed` no fast-check, `withFixedSeed` no QuickTheories, `Replay` no FsCheck. A Forja não impõe, só instrui.

Com `commands.test` no `forja.toml`, o argv do Python deixa de valer e a semente do `--hypothesis-seed` some; as variáveis do Go ficam.

## Arquivos que as ferramentas gravam

`.hypothesis` não conta como mudança da tentativa: a Forja o tira do índice como tira `node_modules`. O Go não grava `testdata\rapid` por causa do `RAPID_NOFAILFILE`.

## O check `properties`

Gate 6, modo observação. Para cada linguagem com arquivo de produção mudado, algum arquivo de teste mudado da mesma linguagem tem de citar a biblioteca (`hypothesis`, `fast-check`, `org.quicktheories`, `pgregory.net/rapid`, `FsCheck`). Senão há um achado por linguagem, no primeiro arquivo de produção dela.

- **Só presença.** Não mede se a propriedade é boa.
- **A linguagem vem do sufixo do arquivo** (`.py`, `.pyi`, `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.java`, `.go`, `.cs`), não do adaptador.
- **Link não conta.** Um teste que é link simbólico ou junção é ignorado, e a leitura de cada arquivo pára em 1 MB.
- **Teste ilegível** torna o resultado `Inconclusive` se a biblioteca não foi achada em outro arquivo.

Para promovê-lo a bloqueante, use `mode = "blocking"` em `[checks.properties]`, com `promotion = { date, reason }` e `on_inconclusive`, como nos outros checks.

## Limites

- **A Forja instrui e mede a presença.** A qualidade da propriedade depende do agente.
- **Custo.** Cada propriedade roda dezenas a centenas de casos, e a mutação refaz os testes a cada mutante.
- **QuickTheories está sem manutenção desde 2019** (última mudança no ramo principal em 15/12/2019; a última versão no GitHub é a 0.25). Rodei um programa mínimo com a 0.25 em JDK 17 e 21: compilou, a falha repetiu com `withFixedSeed`, e `QT_SEED` na propriedade de sistema foi lido. Não testei com JUnit, nem a variável de ambiente `QT_SEED`.
- **Java não tem semente fixada pela Forja** nem `.quicktheories` conhecido em disco; o jqwik não foi escolhido (ADR 0040).
- **Fora do escopo:** teste com estado, fuzzing guiado por cobertura, `testing/quick` do Go.
- **Em aberto para o E2E:** as bibliotecas reais em cada linguagem, a semente do Python e do Go em execução limpa, e o efeito do tempo na mutação.

O plano está em `docs\plano-teste-de-propriedades.md`.
