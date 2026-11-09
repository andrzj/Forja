# Segredos e segurança (gates 2 e 10)

Esta página cobre os dois gates que cuidam do que entra no repositório vindo de fora: o gate 2 (segredos e instalação de dependências) e o gate 10 (análise estática de segurança, vulnerabilidades, licenças e dependências novas). Para o índice dos gates, veja `README.md`. Para as chaves do arquivo de política, veja `..\forja-toml.md`.

| Check | Gate | Modo padrão | Se não puder medir | O que julga |
| --- | --- | --- | --- | --- |
| `secrets` | 2 | bloqueante | bloqueia | segredo nas linhas que a tentativa acrescentou |
| `dependency_install` | 2 | bloqueante | bloqueia | dependência Python nova existe no registro e instala |
| `sast` | 10 | observação | bloqueia | achado novo do Semgrep nos arquivos alterados |
| `dependency_audit` | 10 | observação | bloqueia | vulnerabilidade nova ou licença proibida nas dependências |
| `new_dependency` | 10 | observação | premissa | dependência nova inexistente, recente demais ou pouco usada |

Os três checks do gate 10 nascem em observação: o resultado aparece no resumo, mas não bloqueia a tarefa até você promovê-los (veja "Promover para bloqueio"). Os do gate 2 já bloqueiam.

Dois checks do gate 10 dependem de algo que você fornece. A Forja não traz regras do Semgrep nem lista de licenças. Sem o que é seu, o check não executa, e o resumo da preparação e o da entrega dizem isso em destaque.

## Ferramentas externas

Os checks usam três ferramentas de terceiros: `gitleaks` (segredos), `semgrep` (SAST) e `osv-scanner` (vulnerabilidades e licenças). A Forja instala as três com:

```bash
forja instalar
```

Elas vão para a pasta de dados da Forja (`FORJA_HOME`, veja `..\ambiente.md`), com versão fixada e checksum conferido, e o `PATH` do seu sistema não muda. Uma ferramenta que já está no `PATH` vale e não é instalada de novo. A instalação existe para Windows e Linux; macOS não tem instalação. Detalhes em `..\instalacao.md` e `..\comandos.md`.

O Semgrep é instalado pela Forja num ambiente virtual próprio, a partir do pacote oficial. Você não precisa de `pip install semgrep` nem de pôr o programa no `PATH`. Se preferir uma instalação sua, o `semgrep` no `PATH` também vale.

Para conferir o que falta, rode `forja doctor`. O `gitleaks` sempre entra na lista. O `semgrep` só entra quando há regras configuradas (`--semgrep-config` ou `.semgrep.yml` ou `.semgrep/` no repositório). O `osv-scanner` não tem linha própria no `doctor`; sem ele, a auditoria de dependências fica inconclusiva.

## Gate 2: segredos

### `secrets`

O que faz: passa ao `gitleaks`, com as regras que ele traz, só as **linhas que a tentativa acrescentou**. Remover um segredo nunca reprova a tentativa. O valor encontrado não é copiado para o achado: a próxima tentativa recebe apenas o nome da regra e o arquivo e a linha.

Modo padrão: bloqueante, com `on_inconclusive = "block"`. Não há chaves de limiar, limite nem comando para este check. O `gitleaks` roda sem arquivo de configuração, então `[sensitive]` e `[redaction]` não mudam o que ele acusa.

Ao falhar: a tentativa é reprovada, com a mensagem `a possible secret was added (rule <regra>)` e o lugar. O agente tenta de novo com esse motivo. Se o `gitleaks` não puder rodar ou terminar com erro próprio, o resultado é inconclusivo e, com a política padrão, a tarefa é bloqueada sem contar como falha do agente.

Um comentário que manda a ferramenta ignorar a linha (`gitleaks:allow`, `nosem`, `nosec`, `noqa` e semelhantes) é recusado pelo gate 1: silenciar a ferramenta não passa.

Duas seções do `forja.toml` tratam de segredos por outro caminho:

- `[sensitive]` lista arquivos que nunca chegam ao agente. Os padrões da Forja (`.env`, `*.pem`, `*.key`, `.aws/**` e outros) continuam valendo, e os seus somam a eles.
- `[redaction]` ajusta o mascaramento de segredos e dados pessoais. Os detectores de segredo da Forja nunca são opcionais; você pode acrescentar detectores (`patterns`), liberar valores exatos (`allow`, `allow_patterns`), escolher os tipos de dado pessoal (`pii`) e mudar o limiar de entropia (`entropy_threshold`).

```toml
[sensitive]
paths = [
  "*.keystore",        # em qualquer pasta
  "config/prod/**",    # tudo dentro de config/prod, a partir da raiz
]

[redaction]
pii = ["cpf", "cnpj", "card"]              # e-mail e telefone deixam de ser mascarados
allow = ["fulano@example.com"]             # este valor nunca é mascarado
allow_patterns = ["^TOKEN_DE_TESTE_[A-Z]+$"]
entropy_threshold = 3.0                    # o detector genérico "chave = valor" mascara menos

[redaction.patterns]
chave-interna = "intk_([A-Za-z0-9]{32})"   # o grupo de captura é o segredo
```

O resumo que a Forja mostra antes da confirmação lista o que `[redaction]` afrouxou: valores liberados, tipos de dado pessoal desligados e limiar de entropia mais alto.

### `dependency_install`

O que faz: quando a tentativa acrescenta dependências a um manifesto Python, este check roda antes de todos os outros e prepara o ambiente em que os testes e o build vão rodar.

1. Para cada nome novo, consulta o PyPI. Nome que o registro não lista nunca é instalado.
2. Instala os requisitos novos num ambiente virtual da execução, criado na primeira necessidade a partir do interpretador do repositório. Os pacotes do interpretador do repositório continuam visíveis, atrás dos instalados.
3. O ambiente da Forja e o do repositório não são tocados. O ambiente fica na pasta da execução, a retomada o reencontra e ele não é apagado.

Modo padrão: bloqueante, com `on_inconclusive = "block"`. Não há chaves próprias.

Ao falhar: a tentativa é reprovada com o motivo, que pode ser um destes: o nome não existe no PyPI, o registro não respondeu, o manifesto não pôde ser lido, passaram de 50 dependências novas de uma vez, ou o instalador falhou (a mensagem traz o erro dele). Idade e uso do pacote são julgados depois, pelo `new_dependency`.

O instalador recebe só `PATH`, pastas do usuário, certificados, proxy e as variáveis `PIP_*`. Chaves e tokens não são repassados. Veja `..\ambiente.md`.

O que este check não garante:

- **Instalar executa código do pacote.** Não há sandbox: o código roda com as suas permissões. Um pacote recém-registrado com nome plausível passa na existência, é instalado e só depois o `new_dependency` o reprova por idade.
- O código do pacote ainda roda nos testes, com o ambiente dos testes.

Os agentes que implementam e que escrevem testes podem editar o manifesto, desde que a edição só mude dependências e o manifesto esteja no escopo da tarefa. Em `pyproject.toml` só mudam `project.dependencies`, `optional-dependencies` e `dependency-groups`; em `requirements*.txt` cada linha nova é um requisito simples do registro (sem URL, caminho, opção ou arquivo). Arquivos de trava e manifestos de outras linguagens seguem recusados, porque só o Python tem passo de instalação.

## Gate 10: segurança

### `sast`: análise estática com o Semgrep

O que faz: roda o Semgrep nos arquivos que a tentativa mudou e, numa cópia da árvore devolvida ao commit pai, nas versões antigas desses arquivos. Só reprova o que **aumentou** por arquivo e regra. Achado que já existia não conta, e mover código ou renomear o arquivo não faz um achado antigo parecer novo.

Modo padrão: observação, com `on_inconclusive = "block"`. Não há chaves de limiar, limite nem comando.

#### De onde vêm as regras

A Forja não traz regras. Em ordem de precedência, as regras são:

1. `--semgrep-config CAMINHO` na linha de comando (arquivo ou diretório local).
2. A chave `semgrep_config` do `execucao.toml` (veja `..\execucao-toml.md`).
3. `.semgrep.yml` ou o diretório `.semgrep/` na raiz do **commit base** do repositório.

Regras de registro (`auto`, `p/...`, `r/...`, `s/...`, `semgrep.dev/...` ou qualquer endereço de rede) são recusadas com um erro: a Forja só usa regras locais, para não depender da rede nem de conteúdo que você não revisou. Um caminho que não existe também é erro.

A Forja copia as regras para fora da cópia de trabalho do agente no início da execução. Editar o arquivo de regras numa tentativa não muda o que é escaneado, e o gate de escopo rejeita a mudança de arquivos que não sejam código de produção.

#### Como acrescentar as suas regras

Escreva as regras no formato do Semgrep e salve de um destes modos:

- Um arquivo `.semgrep.yml` na raiz do repositório, com commit. As regras são lidas do commit base, então um arquivo ainda sem commit não vale.
- Vários arquivos dentro de `.semgrep/`, com commit.
- Um arquivo ou diretório fora do repositório, apontado por `--semgrep-config` ou por `semgrep_config`. Útil quando as regras são da equipe e não do projeto.

```yaml
rules:
  - id: shell-true
    pattern: subprocess.$FUNC(..., shell=True, ...)
    message: "shell=True permite injeção de comando"
    languages: [python]
    severity: ERROR
```

Cada regra tem um `id` (o nome que aparece no achado), um `pattern`, uma `message`, as `languages` e uma `severity`. A Forja não filtra por severidade: qualquer achado novo conta. Para escrever as suas, use a documentação do Semgrep: <https://semgrep.dev/docs/writing-rules/overview>. O Semgrep cobre, entre outras, Python, JavaScript, TypeScript, Go, Java e C#.

Para rodar com regras que ficam fora do repositório:

```bash
forja corrigir "o relatório aborta com datas vazias" --semgrep-config regras/semgrep.yml
```

Ou, de forma permanente, no `execucao.toml`:

```toml
semgrep_config = "regras/semgrep.yml"
```

#### Sem regras

Sem regras configuradas o check devolve "não aplicável" e o resumo diz **SAST NÃO EXECUTADO**. Nunca é uma aprovação.

#### Se o Semgrep falha

Código de saída diferente de 0 (por exemplo, um diretório de regras vazio), relatório ilegível, tempo esgotado ou programa ausente dão resultado **inconclusivo**, nunca aprovação. Se o Semgrep roda nos arquivos novos mas não nos antigos, também é inconclusivo.

#### Ao falhar

Cada regra que aumentou num arquivo vira um achado: `<n> new <regra> finding(s)`, com o arquivo, a contagem atual e a anterior. Em observação, o achado só aparece no relatório. Depois de promovido, a tentativa é reprovada e o agente recebe o motivo.

### `dependency_audit`: vulnerabilidades e licenças

O que faz: roda o `osv-scanner` nos arquivos de dependências alterados e, numa cópia com os textos do commit pai, nos antigos. Reprova a combinação (pacote, versão, vulnerabilidade) que existe só no novo. O check só roda quando um destes arquivos mudou:

| Linguagem | Arquivos |
| --- | --- |
| Python | `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pdm.lock`, `uv.lock`, `pylock.toml` |
| JavaScript e TypeScript | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` (o `package.json` não é lido pelo OSV) |
| Go | `go.mod` |
| Java | `pom.xml`, `gradle.lockfile`, `buildscript-gradle.lockfile` |
| C# | `packages.lock.json`, `packages.config`, `deps.json` |

Modo padrão: observação, com `on_inconclusive = "block"`. Não há chaves de limiar, limite nem comando. A única configuração é a lista de licenças proibidas.

O `osv-scanner` precisa de **rede**: vulnerabilidades e licenças vêm de serviços online. Ele também resolve dependências transitivas de alguns arquivos, então o achado pode ser de um pacote que o arquivo não nomeia. Sem rede, ou com o programa ausente, o resultado é inconclusivo.

#### Licenças proibidas: `[licenses]`

Você fornece a lista no `forja.toml` do repositório, com identificadores SPDX. Não há lista padrão.

```toml
[licenses]
forbidden = ["GPL-3.0-only", "AGPL-3.0-only"]
```

- A comparação ignora maiúsculas e minúsculas.
- Uma licença proibida conta mesmo dentro de uma expressão: `MIT OR GPL-3.0-only` reprova, ainda que exista uma opção permitida.
- O identificador não pode ter espaço.
- Só vale licença que **apareceu** com a tentativa; a que o pacote já tinha antes não reprova.

Sem a lista, só as vulnerabilidades são auditadas e o resumo diz **Licenças não verificadas**. Com a lista, um pacote novo sem licença conhecida (`UNKNOWN`, `non-standard`, `NOASSERTION` ou lista vazia) deixa o resultado **inconclusivo**. Se o `osv-scanner` conta uma licença proibida no resumo da varredura e nenhum pacote listado a tem, o resultado também é inconclusivo.

#### Ao falhar

Cada pacote com vulnerabilidade nova vira um achado (`new vulnerability <id> in <pacote> <versão>`, ou a contagem com os três primeiros ids). Cada licença proibida nova vira o achado `forbidden license <licença> in <pacote> <versão>`. Em observação, ficam no relatório; depois de promovido, reprovam a tentativa.

### `new_dependency`: dependência nova inexistente ou suspeita

O que faz: olha o que o manifesto novo tem a mais que o antigo e consulta o registro oficial do ecossistema. Um agente pode inventar um pacote com nome plausível, e alguém pode registrar esse nome depois.

| Ecossistema | Manifestos lidos | Registro |
| --- | --- | --- |
| Python | `pyproject.toml` (dependências, extras e grupos), `requirements*.txt` | PyPI |
| JavaScript e TypeScript | `package.json` (só o que vem do registro; `file:`, `git`, URL e `workspace:` ficam de fora) | npm |
| Go | `go.mod` | proxy do Go |
| Java | `pom.xml`, `build.gradle[.kts]` (notação `"grupo:artefato:versão"`) | Maven Central |
| C# | `*.csproj`, `Directory.Packages.props`, `packages.config` | NuGet |

Modo padrão: observação, com `on_inconclusive = "premise"`. Reprova o pacote que **não existe** no registro, que foi publicado há menos de `min_age_days` dias ou que tem menos de `min_downloads`.

| Chave | Padrão | Efeito |
| --- | --- | --- |
| `thresholds.<linguagem>.min_age_days` | `30` | idade mínima, em dias, desde a primeira publicação. Zero ou mais. |
| `thresholds.<linguagem>.min_downloads` | `100` | mínimo de downloads, onde o registro informa. Zero ou mais. |

A linguagem é uma de `java`, `go`, `python`, `csharp`, `javascript`, `typescript`. Cada linguagem tem o seu valor.

```toml
# Em TypeScript, só aceita pacote com 60 dias e 1000 downloads na última semana.
[checks.new_dependency.thresholds.typescript]
min_age_days = 60
min_downloads = 1000

# Em Python, só a idade importa (o PyPI não mede uso).
[checks.new_dependency.thresholds.python]
min_age_days = 60
```

O que cada registro diz:

- **Uso (downloads):** só o npm (última semana) e o NuGet (total) contam. PyPI, Go e Maven não medem uso, e o resumo avisa isso.
- **Idade no Go:** não é medida, porque a data que o proxy devolve é a do commit, escolhida pelo autor do módulo. Um pacote Go novo dá resultado inconclusivo, que a política padrão registra como premissa no resumo. Só a existência é verificada.
- **Maven:** a busca devolve as versões da mais nova para a mais antiga; um artefato com mais de 1000 versões aparece mais novo do que é.
- **Rede:** sem acesso ao registro o resultado é inconclusivo.
- **Volume:** mais de 50 dependências novas de uma vez dão resultado inconclusivo, em vez de 50 consultas.

Um manifesto que não pode ser lido (XML com declaração de tipo ou entidades, JSON ou TOML inválido, arquivo que não é texto) dá resultado inconclusivo, nunca "sem dependências".

Ao falhar: cada pacote inexistente, recente ou pouco usado vira um achado, por exemplo `<pacote> was first published 3 day(s) ago (minimum 30)`. Este check só reprova ou informa; o registro de decisão que uma dependência nova pede é do documentador.

## O que acontece ao falhar

| Resultado | Observação | Bloqueante, `block` | Bloqueante, `premise` |
| --- | --- | --- | --- |
| Reprovado | aparece no relatório | reprova a tentativa; o motivo vai para a próxima | reprova a tentativa; o motivo vai para a próxima |
| Inconclusivo | aparece no relatório | bloqueia a tarefa; não conta como falha do agente | segue adiante e declara a lacuna como suposição |
| Não aplicável | aparece no resumo como não executado | idem | idem |

Não aplicável não é aprovação. O resumo da preparação e o da entrega dizem em destaque quando o SAST não rodou por falta de regras e quando as licenças não foram verificadas por falta de lista. A tabela completa de modo e política de inconclusivo está em `..\forja-toml.md`.

## Promover para bloqueio

Os checks do gate 10 começam em observação. Para bloquear, promova com uma decisão registrada no `forja.toml`: `mode = "blocking"` mais `promotion`, com `date` e `reason`. Sem `promotion`, o arquivo é recusado.

```toml
# Torna o SAST bloqueante. Ele nasce em observação, então a promoção
# precisa de data e motivo.
[checks.sast]
mode = "blocking"
promotion = { date = 2030-01-31, reason = "regras revisadas em 30 PRs sem falso positivo" }

# A auditoria de dependências também. Se o osv-scanner não puder rodar
# (sem rede, por exemplo), a tarefa para em vez de seguir sem a medição.
[checks.dependency_audit]
mode = "blocking"
on_inconclusive = "block"
promotion = { date = 2030-01-31, reason = "licenças proibidas listadas em [licenses]" }

# Dependência nova: bloqueia, e o que não puder ser medido (registro fora do ar)
# segue como premissa declarada no resumo.
[checks.new_dependency]
mode = "blocking"
on_inconclusive = "premise"
promotion = { date = 2030-01-31, reason = "limiares de idade e uso revistos" }

[licenses]
forbidden = ["GPL-3.0-only", "AGPL-3.0-only"]
```

Pontos de atenção antes de promover:

- Promova `sast` só com as suas regras já revisadas. Em bloqueio, um achado novo reprova a tentativa, e um falso positivo vira tentativa perdida.
- Promova `dependency_audit` com a lista `[licenses]` definida; sem ela, só vulnerabilidades bloqueiam.
- Os padrões de `new_dependency` (30 dias, 100 downloads) não foram calibrados com dados reais. Confira os limiares por linguagem antes de bloquear.
- `on_inconclusive = "block"` para a tarefa quando a ferramenta ou a rede falham; `"premise"` segue adiante e declara a lacuna. Com o padrão de cada check (`block` em `sast` e `dependency_audit`, `premise` em `new_dependency`) você não precisa escrever a chave.
- Os checks do gate 2 já bloqueiam. Para afrouxar um deles não é preciso `promotion`: `mode = "observation"` basta, e ele passa a só reportar.

A promoção aparece no resumo que a Forja mostra antes da confirmação (`<id>: promovido de observação a bloqueio (<data>)`). Mudar o `forja.toml` entre pausar e retomar uma execução faz a Forja recusar a retomada. Veja `..\forja-toml.md`.

## Resumo das chaves

| Chave | Check | Padrão |
| --- | --- | --- |
| `[checks.<id>] mode`, `on_inconclusive`, `promotion` | os cinco | veja a tabela do início da página |
| `[checks.new_dependency.thresholds.<linguagem>] min_age_days` | `new_dependency` | `30` |
| `[checks.new_dependency.thresholds.<linguagem>] min_downloads` | `new_dependency` | `100` |
| `[licenses] forbidden` | `dependency_audit` | vazia (licenças não verificadas) |
| `[sensitive] paths` | arquivos que não chegam ao agente | só os padrões da Forja |
| `[redaction] patterns`, `allow`, `allow_patterns`, `pii`, `entropy_threshold` | mascaramento de segredos e dados pessoais | veja `..\forja-toml.md` |
| `semgrep_config` (`execucao.toml`) e `--semgrep-config` | `sast` | regras do commit base, se houver |

`secrets`, `dependency_install`, `sast` e `dependency_audit` não têm limiares, limites nem comandos: o `forja.toml` aceita neles só `mode`, `on_inconclusive` e `promotion`. Para a instalação das ferramentas, veja `..\instalacao.md`; para os comandos, `..\comandos.md`.
