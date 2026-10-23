# Plano: gate 6, E2E com rede desligada

Estado: plano, nada implementado; sem perguntas abertas. Regra do dono: gates grandes só com plano escrito antes. Este vem antes do gate 9 e é pré-requisito do gate 11.

## O que a Especificação diz

- Tabela de gates, linha 6: reprova quando o E2E **falha, ou tentou acesso à rede** (os E2E rodam com rede desligada).
- Seção "E2E sem ambiente real": fakes antes de mocks; **rede desligada** (dependência de serviço real faz o teste falhar, o que prova mecanicamente o isolamento); fakes honestos (gerados ou validados por contrato; sem contrato, a divergência possível vira **premissa no resumo**); determinismo (relógio fake, sementes fixas); **sem dados reais**: fixtures vêm de geradores com semente, declarados no manifesto de testes, e **um scanner verifica padrões de dados pessoais** (CPF, e-mail, telefone).
- Seção "Níveis": o especificador atribui o nível de cada critério; fluxo de ponta a ponta exige E2E; E2E inviável com justificativa vira premissa no resumo (papel do incremento 6, fora deste plano).
- Seção "Ambiente do usuário": a Forja **não cria sandbox**; a rede é "do ambiente"; nenhuma ferramenta depende de WSL ou Linux; E2E executa código não confiável no ambiente do usuário. Plano de execução, incremento 5: "E2E com fakes e rede desligada"; pronto quando "um E2E que acessa rede falha".
- Regras gerais: check novo nasce em observação; ferramenta que falha é `Inconclusive`; o que o usuário deve fornecer e não forneceu **não executa e o resumo diz** (ADR 0024).

## O que o código tem hoje (lido em 23/10)

- `Operation.E2E` e `LanguageCapability.E2E` existem; **nenhum dos cinco adaptadores os implementa** (`plan` devolve `NotSupported`). `core\policy\config.py` já aceita `e2e` entre as chaves de comando que o repositório pode sobrescrever, mas `plan_with_override` só vale onde o adaptador suporta a operação, então hoje a chave não tem efeito.
- `CommandPlan.env_set` chega ao processo pelo `build_spec` (ambiente filtrado por lista de permissões). `Tools.run(check, plan)` é o caminho de build e testes.
- `DataGenerator(name, seed, path)` e `AuthoredTestsBody.generators` existem no esquema do manifesto de testes; **nada os executa**, e o autor de testes (incremento 6) não existe.
- Os detectores de dados pessoais existem em `core\redaction\pii.py` (`DETECTORS`, `PiiKind`), usados na redação; não há scanner de arquivos de teste.
- Garantia `NETWORK_ALLOWLIST` em `core\isolation\levels.py` está no estado "do ambiente".

## Decisões

1. **Um check por assunto, os dois no gate 6:** `e2e` (executa e reprova falha ou tentativa de rede) e `test_data` (dados pessoais em teste e fixture). Os dois nascem em `Mode.OBSERVATION`; `e2e` com política `BLOCK` para "não consegui medir", `test_data` com `PREMISE`.
2. **De onde vem o comando.** E2E não tem ferramenta própria: o comando é o que o repositório declara em `[commands.<linguagem>] e2e = [...]` no `forja.toml`. O plano de execução é o `plan(Operation.TEST)` do adaptador (diretório, ambiente, interpretador) com o `argv` trocado pelo declarado, e a saída é lida pelo `parse(Operation.TEST)` do adaptador. Sem comando declarado em nenhuma linguagem: `NotApplicable`, e os resumos da preparação e da entrega dizem em destaque **"E2E não executado: sem comando"**. Não é inventado comando padrão.
3. **Rede desligada, sem sandbox.** O que a Forja impõe e funciona em qualquer sistema: **armadilha de proxy**. Para cada execução de E2E a Forja abre um servidor TCP em `127.0.0.1` numa porta efêmera, fora da worktree, e entrega ao processo `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (maiúsculas e minúsculas) apontando para ele, com `NO_PROXY=localhost,127.0.0.1,::1` (os fakes em loopback continuam alcançáveis). Cliente que respeita proxy e tenta sair de loopback cai na armadilha, que registra o **destino (host e porta, nunca caminho nem parâmetros)**, responde recusando e fecha. Qualquer registro reprova a tarefa com "tentou acesso à rede: host:porta", **mesmo que os testes passem**. Mais, por ecossistema, as chaves de modo offline do próprio gerenciador (lidas e testadas no passo 0). Isto é mecânico e multiplataforma, mas **não é contenção**: cliente que ignora o proxy (soquete cru, Java sem propriedades de proxy, resolvedor de DNS) não é visto. O passo 0 mede, por linguagem, quais clientes honram o proxy e o que se faz para cobri-los (ex.: `JAVA_TOOL_OPTIONS` com `-Dhttp.proxyHost`); o que sobrar vira limite declarado no resumo ("rede desligada por proxy; não impede cliente que o ignora; contenção forte é do ambiente"). A garantia continua `Do ambiente` na declaração da preparação, com linha extra para o E2E.
4. **Fakes honestos.** A Forja não valida contrato (OpenAPI, Pact) nesta etapa. Quando o E2E roda, o resumo traz sempre a premissa **"fakes não validados por contrato"**, como a Especificação manda para fake sem contrato. Validação por contrato fica para quando houver o papel que gera fakes.
5. **Determinismo.** Relógio fake e sementes são do teste; a Forja só garante o que lhe cabe: o E2E roda duas vezes na medição da base, e teste que difere entre as duas vai para a quarentena já existente (o mesmo critério da suíte instável), nunca reprova a tentativa.
6. **Scanner de dados pessoais (`test_data`).** Roda sobre os arquivos de teste e de fixture mudados (a classificação já é do adaptador), com os detectores de `core\redaction\pii.py` (CPF com dígitos verificadores, e-mail, telefone). Achado novo (catraca por arquivo e tipo, como os outros checks) reprova em observação; a mensagem diz tipo e arquivo, **nunca o valor**. Domínios reservados (`example.com`, `.test`, `.invalid`) e números que falham no dígito verificador não contam. Geradores com semente declarados no manifesto de testes são do autor de testes (incremento 6), não deste plano.
7. **Timeout e processos.** O E2E usa `Tools.run`, então herda o Job Object, o ambiente filtrado e o tempo máximo (chave própria `e2e` em `timeouts`, padrão do `DEFAULT_TIMEOUT`).
8. **Não faz parte:** nível por critério e E2E obrigatório (especificador); geradores e manifesto (autor de testes); contêiner de fakes (WireMock e afins são dependências do projeto); contenção de rede por sistema operacional.

## Passos (um commit cada)

0. **Ler e medir:** documentação de proxy por ecossistema (`urllib`/`requests`, `net/http` com `ProxyFromEnvironment`, Node (`NODE_USE_ENV_PROXY`, já visto em `executors\cursor.py`), .NET `HttpClient`, JVM) e das chaves offline (`GOPROXY=off`, `npm_config_offline`, Maven `-o`, Gradle `--offline`, NuGet, `PIP_NO_INDEX`). Com as ferramentas reais, em projetos descartáveis no scratchpad, medir para cada linguagem: o cliente padrão chega à armadilha? o que é preciso passar? Corrigir este plano com o que divergir, inclusive a lista de limites do item 3.
1. **Armadilha:** `checks\network_trap.py` (servidor assíncrono em loopback, registro de destinos, parada limpa, só o primeiro pedaço da primeira linha é lido e limitado em tamanho; `CONNECT host:port` e URI absoluta). Testes com clientes reais da biblioteca padrão do Python: passa em loopback sob `NO_PROXY`, cai na armadilha fora dele.
2. **Plano de E2E:** função que monta o `CommandPlan` (TEST do adaptador, `argv` declarado, `env_set` do proxy e do modo offline); `CheckSpec("e2e", 6, OBSERVATION, BLOCK, commands={"e2e"})`; leitura de `[commands.<linguagem>] e2e`. Testes com adaptadores falsos.
3. **`E2ECheck`:** roda por linguagem, junta os resultados (`EachLanguage` não, pois o plano já é por adaptador, como `TestsCheck`); reprova teste falho, teste que passou na base e sumiu, e destino na armadilha; ferramenta que não inicia, relatório ilegível ou armadilha que não abriu: `Inconclusive`. Duas execuções na base e quarentena (decisão 5).
4. **`PiiCheck` (`test_data`):** o scanner da decisão 6, com `CheckSpec("test_data", 6, OBSERVATION, PREMISE)`.
5. **Integração:** os dois checks no `PipelineMeasurer.judge` (depois de `new_dependency`), `notices` ("E2E não executado: sem comando", "fakes não validados por contrato", limite do proxy), resumo da preparação e da entrega, política (`timeouts`).
6. **Documentação do usuário e ADR:** como declarar o comando de E2E, o que a armadilha vê e o que não vê, o que fica do ambiente, onde ficam os dados pessoais e as exceções do scanner. ADR (rede desligada por armadilha de proxy, sem sandbox).
7. **Ponta a ponta real** (regra do dono: só no fecho do gate) e **gate de mutação no WSL** nos arquivos novos. E2E real por linguagem: teste contra fake em loopback passa; teste que alcança host externo por cliente que honra o proxy reprova com o destino.

## Leitura do passo 0 (23/10, parte medida)

Armadilha em loopback (recusa com 403 e registra a primeira linha), `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (e minúsculas) apontando para ela, alvo `blocked.test` (sem DNS). Windows, Python 3.11, Go 1.27.3, Node 26.12.1, .NET 9.0.319, JDK 21.0.12.

| Cliente | Chega à armadilha? | Registro visto |
|---|---|---|
| Python `urllib.request` | sim | `GET http://host/…` e `CONNECT host:443` |
| Python `http.client` | **não** (resolve DNS direto) | nada |
| Go `net/http` | sim | idem |
| Go `net.Dial` cru | não | nada |
| Node `fetch`, `http`, `https` | **só com `NODE_USE_ENV_PROXY=1`**; sem ela, não | idem |
| Node `net.connect` cru | não | nada |
| .NET `HttpClient` | sim | idem |
| .NET `TcpClient` cru | não | nada |
| Java `HttpURLConnection` e `java.net.http.HttpClient` | **não** com as variáveis; **sim** com `-Dhttp.proxyHost/Port`, `-Dhttps.proxyHost/Port`, `-Dhttp.nonProxyHosts` em `JAVA_TOOL_OPTIONS` | idem |

Consequências para o plano (corrigem a decisão 3):
- O ambiente do E2E acrescenta, além das variáveis de proxy, **`NODE_USE_ENV_PROXY=1`** (Node) e **`JAVA_TOOL_OPTIONS`** com as propriedades de proxy da JVM (`nonProxyHosts=localhost|127.0.0.1`). O `JAVA_TOOL_OPTIONS` do usuário, se houver, é preservado e acrescido, e a JVM imprime "Picked up JAVA_TOOL_OPTIONS" no stderr (ruído aceito).
- O registro é `GET http://host/…` (só host e porta saem da linha) ou `CONNECT host:porta`; a armadilha lê só essa linha.
- Continuam fora da vista: soquete cru em qualquer linguagem e Python `http.client` (e o que o usa por baixo, a depender da biblioteca). Entram no limite declarado do resumo. Medir `requests` e `httpx` (Python) fica para o passo 6, com a ferramenta real do ponta a ponta.
- Falta do passo 0: ler a documentação e medir as chaves de modo offline (`GOPROXY=off`, `npm_config_offline`, Maven `-o`, Gradle `--offline`, NuGet, `PIP_NO_INDEX`); **ainda não feito**, e o passo 2 não deve usar nenhuma antes disso. Scripts da medição: scratchpad da sessão (`g6\`), fora do repositório.

## Limites já conhecidos

- Não é contenção: cliente que ignora o proxy sai sem ser visto; a Especificação diz que a rede é do ambiente e que quem precisa de contenção forte roda a Forja já dentro dela.
- Sem comando de E2E declarado, o gate não executa (e diz).
- Sem contrato, o fake pode divergir do serviço real; fica registrado como premissa, não medido.
- O scanner acha padrões, não prova ausência de dado real.
