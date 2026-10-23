# E2E com rede desligada e dados de teste (gate 6)

O gate 6 tem dois checks: `e2e` e `test_data`. Os dois nascem em **modo observação**: o resultado aparece no resumo, mas não bloqueia a tarefa até você promovê-los (veja "Promover para bloqueio" em [segurança e dependências](seguranca-e-dependencias.md); a seção é a mesma, com `[checks.e2e]` e `[checks.test_data]`).

## E2E: o comando é seu

A Forja não traz comando de E2E e não inventa um. Você declara, por linguagem, no `forja.toml` do repositório:

```toml
[adapters.python.commands]
e2e = ["pytest", "tests/e2e"]

[adapters.typescript.commands]
e2e = ["npx", "vitest", "run", "e2e"]
```

O comando roda com o diretório, o ambiente e o interpretador do plano de testes do adaptador da linguagem, e a saída é lida como a de qualquer execução de testes. Em monorepo, roda uma vez por projeto da linguagem.

Sem comando em nenhuma linguagem o check devolve “não aplicável” e o resumo diz **“E2E não executado: sem comando”**. Nunca é uma aprovação.

### O que reprova

- teste de E2E que falha;
- teste de E2E que passava na base e sumiu ou deixou de passar;
- **tentativa de acesso à rede**, mesmo que todos os testes tenham passado. A mensagem traz o destino (`host:porta`), nunca caminho nem parâmetros.

Testes de E2E que mudam de resultado entre as duas execuções da base vão para a quarentena e não reprovam a tentativa. A base também roda o E2E duas vezes; falha ou tentativa de rede na base é registrada como problema da base, como acontece com teste que falha na base.

### Como a rede é desligada (e o que isso não é)

A Forja **não cria sandbox** (ADR 0018). Para cada execução de E2E ela abre uma **armadilha de proxy** em `127.0.0.1`, numa porta efêmera, e entrega ao processo `HTTP_PROXY`, `HTTPS_PROXY` e `ALL_PROXY` (maiúsculas e minúsculas) apontando para ela, com `NO_PROXY=localhost,127.0.0.1,::1` (fakes em loopback continuam alcançáveis). Cliente que respeita o proxy e tenta sair cai na armadilha, que registra o destino, recusa (403) e fecha. Além disso:

| Variável | Para quê |
|---|---|
| `NODE_USE_ENV_PROXY=1` | O Node ignora as variáveis de proxy sem ela |
| `JAVA_TOOL_OPTIONS` com `-Dhttp.proxyHost` e afins | A JVM só respeita as propriedades próprias; o valor que você já tinha é preservado e acrescido |
| `npm_config_offline=true`, `PIP_NO_INDEX=1`, `GOPROXY=off` | Modo offline dos gerenciadores |

Medido com clientes reais (Windows, 23/10/2026): Python `urllib`, Go `net/http` e .NET `HttpClient` honram o proxy; Node e Java honram com as chaves acima.

**Não é contenção.** Não são vistos: soquete cru em qualquer linguagem e Python `http.client` (resolve DNS direto). `GOPROXY=off` é a chave documentada do Go, mas não ficou provado que ela barra o download. Maven, Gradle e NuGet ficam só com a armadilha (`-o` e `--offline` são argumentos do comando, que é seu). Quem precisa de contenção forte roda a Forja já dentro de um ambiente sem rede. O resumo diz isso em toda execução com E2E.

### Fakes

A Forja não valida fakes por contrato. Toda execução com E2E registra no resumo a premissa **“fakes não validados por contrato; podem divergir do serviço real”**. Relógio fake e sementes fixas são do teste; a Forja só garante o que lhe cabe (as duas execuções da base).

### Tempo máximo

O E2E usa o mesmo executor das demais ferramentas (Job Object, ambiente filtrado e tempo máximo). A chave de tempo é `e2e`; a sessão ainda não lê tempos da política, então vale o padrão.

## Dados pessoais em teste e fixture (`test_data`)

O check lê os arquivos de teste e de fixture que a tentativa mudou (a classificação é do adaptador) e procura, com os detectores da redação, **CPF, CNPJ, e-mail, telefone e cartão**. Reprova só o que **aumentou** por arquivo e tipo em relação ao commit pai; mover linha ou renomear o arquivo não torna dado antigo “novo”. A mensagem diz o tipo e o arquivo, nunca o valor.

Não contam: CPF, CNPJ e cartão que falham no dígito verificador ou no Luhn; e-mail em domínio reservado (`example.com`, `example.org`, `example.net`, `localhost`, `.test`, `.invalid`, `.example`, `.localhost`, `.local`); telefone fora dos DDDs válidos. Arquivo ilegível dá resultado inconclusivo (política: premissa no resumo).

Onde ficam os dados: use valores sintéticos (CPF com dígitos que não fecham, domínios reservados). **Não há lista de exceções por repositório** nesta versão. Geradores com semente declarados no manifesto de testes pertencem ao autor de testes, ainda não construído.

O scanner acha padrões; não prova ausência de dado real.
