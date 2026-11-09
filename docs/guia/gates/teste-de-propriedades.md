# Teste de propriedades

O gate 6 inclui o check `properties`. Ele verifica se a tentativa que mudou código de produção trouxe também um teste de propriedades, e a Forja instrui o autor de testes a escrever um quando o código se presta a isso. O check nasce em **modo observação**: o resultado aparece no resumo e nunca bloqueia a tarefa até você promovê-lo. O índice dos gates está em `README.md`; as chaves do `forja.toml` estão em `..\forja-toml.md`.

## O que é

Um teste de propriedades afirma uma regra que vale para qualquer entrada e deixa uma biblioteca tentar muitas entradas. É um teste comum do executor de cada linguagem, sem executor próprio, e roda junto dos demais testes, sob os gates que já medem testes.

## Uma biblioteca por linguagem

| Linguagem | Biblioteca | Como o agente a usa |
| --- | --- | --- |
| Python | Hypothesis | `@given(...)` num teste do pytest |
| TypeScript | fast-check com `@fast-check/vitest` | `test.prop([fc.integer()])("regra", ...)` |
| Java | QuickTheories | `qt().forAll(...).check(...)` num teste JUnit |
| Go | `pgregory.net/rapid` | `rapid.Check(t, func(t *rapid.T) { ... })` |
| C# | FsCheck com `FsCheck.Xunit` | `[Property]` num método |

São dependências de teste do repositório, não ferramentas da Forja. O agente as acrescenta ao manifesto de dependências do projeto, e a Forja não instala nada por conta própria para isso.

## O que o agente recebe

Só o autor de testes recebe a seção `## Property tests` na instrução, com a biblioteca de cada linguagem detectada no repositório. O texto é fixo e diz quando escrever uma propriedade:

- função pura cujo resultado segue uma regra (ordenar, interpretar, normalizar, calcular);
- par que se desfaz (codificar e decodificar): a ida e volta devolve a entrada;
- invariante (um total nunca fica negativo, o resultado fica dentro de uma faixa, a ordem se mantém);
- função que tem uma versão mais simples e mais lenta para comparar.

Linguagem sem biblioteca da Forja não recebe instrução. A instrução cobre Python, TypeScript, Java, Go e C#. JavaScript não aparece nela, embora o check reconheça arquivos de JavaScript (veja "Como o check decide").

## O check `properties`

Para cada linguagem com arquivo de produção mudado, algum arquivo de teste mudado da mesma linguagem tem de citar a biblioteca. O check procura o texto abaixo, e maiúsculas e minúsculas contam:

| Linguagem | Texto procurado no arquivo de teste |
| --- | --- |
| Python | `hypothesis` |
| TypeScript e JavaScript | `fast-check` |
| Java | `org.quicktheories` |
| Go | `pgregory.net/rapid` |
| C# | `FsCheck` |

Quando nenhum arquivo de teste mudado cita a biblioteca, há um achado por linguagem, no primeiro arquivo de produção dela, com a mensagem `no <linguagem> property test (<texto>) in changed tests`. Se a tentativa não mudou código de produção em nenhuma linguagem coberta, o check passa.

### Como o check decide

- **Só presença.** O check mede se a biblioteca aparece no texto de um teste mudado. Não mede se a propriedade é boa, nem prova que a biblioteca roda: um teste que apenas cita o nome (num `import` ou num comentário) satisfaz o check.
- **A linguagem vem do sufixo do arquivo**, não do adaptador: `.py` e `.pyi` (Python); `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs` e `.cjs` (TypeScript e JavaScript, que usam a mesma biblioteca); `.java`; `.go`; `.cs`. Um arquivo de produção com outro sufixo não exige nada.
- **Só vale teste mudado pela tentativa.** O arquivo de teste (ou de apoio a teste, como a linguagem o classifica) tem de existir depois da mudança e ter sido tocado por ela. Um teste de propriedades que já estava no repositório e não foi mudado não conta.
- **Link não conta.** Um teste que é link simbólico ou junção é ignorado.
- **Só o começo do arquivo.** A leitura de cada arquivo para em 1 MB.
- **Teste ilegível.** Se algum teste não pôde ser lido e a biblioteca não foi achada em outro, o resultado é inconclusivo, não reprovado: a Forja não toma o que não conseguiu ler por falta.

### O que acontece ao falhar

O modo padrão é `observation`, com `on_inconclusive = "premise"`:

| Resultado | Em observação (padrão) | Promovido, `on_inconclusive = "premise"` | Promovido, `on_inconclusive = "block"` |
| --- | --- | --- | --- |
| Biblioteca achada, ou nada de produção mudou | passa | passa | passa |
| Biblioteca ausente | aparece no relatório; a tentativa segue | reprova a tentativa; o motivo vai para a próxima | reprova a tentativa; o motivo vai para a próxima |
| Teste ilegível | aparece no relatório | segue e declara a lacuna como suposição | bloqueia a tarefa; não conta como falha do agente |

A regra geral de modo e inconclusivo está em `..\forja-toml.md`.

## Chaves e padrões

O check aceita só as chaves comuns a toda verificação. Não tem limiar, limite nem comando próprios.

| Chave | Padrão | Efeito |
| --- | --- | --- |
| `mode` | `observation` | `blocking` faz a ausência da biblioteca reprovar a tentativa |
| `on_inconclusive` | `premise` | o que fazer quando um teste não pôde ser lido; só tem efeito com `mode = "blocking"` |
| `promotion` | ausente | obrigatória ao promover; `{ date, reason }` |

Uma chave `thresholds`, `limits` ou `commands` em `[checks.properties]` é erro: a Forja recusa o arquivo com mensagens como `checks.properties.thresholds.python.<nome>: this check has no such threshold`, `checks.properties.limits.<nome>: this check has no such limit` e `checks.properties.commands.<nome>: this check has no such command`.

## Promover para bloqueio

Para o check reprovar a tentativa que muda código de produção sem teste de propriedades, mude `mode` para `blocking` e registre a decisão em `promotion`. O procedimento completo, com a regra de quando `promotion` é obrigatória ou proibida, está em [segurança e dependências](seguranca-e-dependencias.md#promover-para-bloqueio).

```toml
# Torna o check bloqueante. Ele nasce em observação, então a promoção
# precisa de data e motivo.
[checks.properties]
mode = "blocking"
on_inconclusive = "premise"   # teste ilegível não bloqueia; a lacuna segue declarada
promotion = { date = 2030-01-31, reason = "o repositório passou a ter propriedades nas funções de cálculo" }
```

Sem `promotion`, a Forja recusa o arquivo com `promoting a check from observation to blocking needs a recorded decision`. Com `on_inconclusive = "block"`, um teste ilegível bloqueia a tarefa em vez de seguir com a lacuna declarada:

```toml
[checks.properties]
mode = "blocking"
on_inconclusive = "block"
promotion = { date = 2030-01-31, reason = "propriedade é exigida em todo código de cálculo" }
```

Manter o modo padrão e deixar a política de inconclusivo guardada para o dia da promoção também é aceito:

```toml
# Continua em observação. O valor só passa a valer se o check virar bloqueante.
[checks.properties]
on_inconclusive = "block"
```

## Semente

Teste aleatório sem semente fixa quebra a repetição que a Forja faz do mesmo teste (linha de base, cabeça da tentativa, mutação): a mesma propriedade poderia passar numa execução e falhar noutra. A Forja fixa a semente onde a ferramenta permite, sem editar o teste. O valor é fixo e único.

| Linguagem | O que a Forja faz |
| --- | --- |
| Python | acrescenta `--hypothesis-seed=<valor>` ao `pytest`, nos testes e na cobertura. Só quando `pyproject.toml` (dependências do projeto, extras opcionais ou grupos de dependências) ou algum `requirements*.txt` na raiz do projeto declara `hypothesis`. A opção pertence ao plugin e daria erro de uso sem ele. |
| Go | define as variáveis `RAPID_SEED` e `RAPID_NOFAILFILE=true` no ambiente dos comandos |
| TypeScript, Java, C# | não injeta nada. A instrução manda o agente fixar a semente no próprio teste: `seed` no fast-check, `withFixedSeed` no QuickTheories, `Replay` no FsCheck. A Forja não impõe isso, só instrui. |

O nome do pacote no manifesto é comparado sem diferenciar maiúsculas e tratando `-`, `_` e `.` como iguais, então `Hypothesis` e `hypothesis` valem.

Quando o repositório define o comando de teste em `[checks.tests.commands]`, o comando do Python é o seu e a opção `--hypothesis-seed` não é acrescentada. As variáveis do Go continuam, porque pertencem ao ambiente e não ao comando. Para manter a semente fixa no Python com comando próprio, escreva a opção nele:

```toml
# O repositório roda os testes por um comando próprio e mantém a semente fixa.
[checks.tests.commands]
test = ["python", "-m", "pytest", "-q", "-x", "--hypothesis-seed=12345"]

[checks.red_green.commands]
test = ["python", "-m", "pytest", "-q", "-x", "--hypothesis-seed=12345"]
```

O comando de teste vale para todas as linguagens do projeto, como descrito em `..\forja-toml.md`.

## Arquivos que as ferramentas gravam

O diretório `.hypothesis`, onde o Hypothesis guarda seus exemplos, não conta como mudança da tentativa: a Forja o ignora como ignora `node_modules`. O Go não grava `testdata\rapid` por causa de `RAPID_NOFAILFILE`.

## Limites

- **A Forja instrui e mede a presença.** A qualidade da propriedade depende do agente.
- **O check procura o nome da biblioteca no texto dos testes.** Não confirma que a biblioteca está instalada nem que a propriedade executa.
- **Custo.** Cada propriedade roda dezenas a centenas de casos, e a mutação refaz os testes a cada mutante.
- **QuickTheories não tem manutenção desde 2019.** É a biblioteca que a Forja indica para Java.
- **Java não tem semente fixada pela Forja.** Para fixá-la, o teste usa `withFixedSeed`.
- **JavaScript.** O check aceita `fast-check` em arquivos de JavaScript, mas a instrução ao agente só cita a biblioteca de TypeScript.
- **Fora do escopo:** teste com estado, fuzzing guiado por cobertura e o `testing/quick` do Go.
