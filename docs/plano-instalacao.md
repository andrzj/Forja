# Plano: instalação das ferramentas externas e instalação da Forja

Estado: plano, nada implementado. Origem: ordem do dono em 02/11/2026. A Forja precisa **instalar** as ferramentas de terceiros de que o fluxo completo depende, e todas têm de ser software livre (OSS). O usuário deve instalar a Forja de uma forma só e depois usá-la por um comando ou pela UI, sem preparar o ambiente à mão. O que foi decidido e escrito antes em sentido contrário está invalidado por esta ordem.

## O que esta ordem invalida

- ADR 0017, linha "`forja doctor` verifica e explica; não instala", e a frase "instalação assistida de ferramentas [...] ficam para depois". O ADR do passo 1 substitui essa parte.
- `docs\estado.md`: a nota de que o `doctor` verifica e aponta a correção, mas não instala nada.
- O docstring de `src\forja\cli\doctor.py` ("Nothing is installed here") e as mensagens `fix` de cada item, que hoje mandam o usuário a um site.
- O README, que hoje só descreve o ambiente de desenvolvimento da Forja (`uv sync`).

Continua valendo: a Forja não instala a CLI do agente nem faz o login do usuário (`doctor.py`, `_agent_check`). Pela regra "sempre OSS", o Claude Code fica de fora; instalar e autenticar a CLI do agente é do usuário.

## Ferramentas de terceiros que o fluxo exige

Levantadas em 02/11/2026 em `pyproject.toml`, `cli\doctor.py` e `src`. A lista é a de partida do passo 0, que confirma cada uma e a licença.

- **Já vêm com a Forja (dependências Python):** pydantic, rich, textual, tree-sitter e as seis gramáticas, lizard, ruff.
- **Transversais, em toda execução:** gitleaks, semgrep (quando há regras), osv-scanner, jscpd (fila 13). O **git** é o único que a Forja não instala: é pré-requisito do usuário (ordem do dono, 02/11/2026); o `doctor` só o verifica e aponta onde instalar.
- **Por linguagem do repositório alvo (lista de partida; corrigida na leitura do passo 0):** Go: go, golangci-lint. TypeScript/JavaScript: node. C#: SDK dotnet. Java: JDK, Maven ou Gradle. Python: nada além do ambiente do repositório.

## Leitura do passo 0 (02/11/2026, feita)

Lida a documentação oficial de cada ferramenta e, no código da Forja, como cada uma é chamada. **Os checksums não são gravados aqui:** os valores vieram resumidos por modelo e o passo 2 os lê direto dos arquivos oficiais ao fixar a versão.

| Ferramenta | Licença | Instalação oficial (Windows x64, Linux x64) | Checksum e assinatura publicados | Candidata a fixar |
| --- | --- | --- | --- | --- |
| gitleaks | MIT | binário do release (zip, tar.gz); sem runtime | `gitleaks_<v>_checksums.txt` no release; algoritmo não lido | 8.30.1 (21/03/2026); o README diz "feature complete", só correções de segurança |
| osv-scanner | Apache-2.0 | binário do release; sem runtime | `osv-scanner_SHA256SUMS`; proveniência SLSA3 | 2.7.0 (12/10/2026) |
| jscpd | MIT | tar.gz do release (binário autossuficiente, v5) ou wheel do PyPI; Node não é necessário | `checksums.txt`, assinaturas sigstore, SLSA | 5.4.2 (20/10/2026) |
| semgrep | LGPL-2.1 | só pacote Python (wheel, Python 3.10 ou mais); sem binário avulso documentado; suporte a Windows nativo não documentado | sha256 por arquivo no PyPI | 1.183.0 (29/10/2026) |
| go (com gofmt) | BSD-3-Clause | zip e tar.gz em `go.dev/dl`; extração sem administrador não documentada | SHA-256 em `go.dev/dl` | 1.27.3 (19/10/2026) |
| golangci-lint | GPL-3.0 | binário do release; o script `curl \| sh` é vedado pela decisão 3 | `*-checksums.txt` no release; assinatura não documentada | 2.15.0 (16/10/2026) |
| node | MIT (npm: Artistic-2.0) | zip e tar do diretório oficial de releases; se o npm vem dentro do pacote, não verificado | `SHASUMS256.txt` e `.asc` (PGP) | 26.13.0 (LTS) |
| SDK dotnet | MIT | zip e tar.gz, ou `dotnet-install` com `-InstallDir` e `-NoPath` | SHA-512 em arquivo oficial; o script tem assinatura GPG | 10.0.403 (LTS, 25/10/2026) |
| JDK (Temurin) | GPLv2 com Classpath Exception | zip e tar.gz, sem administrador | SHA-256 e assinatura GPG por arquivo | LTS 21 ou 25, escolha no passo 2: o template Maven da Forja usa `release` 17 e o Gradle 9.8.2 aceita JVM 17 a 27 |
| Maven | Apache (a página de instalação não nomeia) | zip e tar.gz; exige JDK 8 ou mais | SHA-512 e PGP | 3.10.0 (27/09/2026) |
| Gradle | Apache-2.0 | zip `bin`; JVM 17 a 27; só se o repositório não tem `gradlew` | SHA-256; assinatura não documentada | 9.8.2 |

**Correções à lista de partida** (pelo código da Forja):

- Não são da Forja, vêm do projeto alvo: prettier, eslint, typescript, vitest, jest e a cobertura Istanbul/c8 (a Forja chama os de `node_modules` do projeto); coverlet (pacote NuGet do projeto); JaCoCo e Checkstyle (o Maven ou o Gradle do projeto os baixa).
- O `npm` só entra pelo pacote do Node, se vier dentro dele.

**Em aberto para os passos 2 e 3 (o que cabia ao passo 2 está resolvido em "Manifesto de ferramentas"):** npm dentro do pacote do Node; extração do Go sem administrador; semgrep em Windows nativo; algoritmo dos checksums de gitleaks e jscpd; o Python do semgrep sai do Python da própria Forja (3.12, acima do mínimo 3.10 do semgrep), em ambiente virtual próprio na pasta da Forja; Checkstyle e licença do Maven sem confirmação (fora do manifesto, não afeta).

## Decisões

1. **A Forja instala as ferramentas externas OSS do fluxo completo, exceto o git.** As transversais sempre que faltarem; as de linguagem só para as linguagens detectadas no repositório. Ferramenta que o passo 0 mostrar que não é OSS sai da lista e é dita ao dono.
2. **Instalação isolada, sem administrador.** Tudo vai para uma pasta da Forja no `<home>` do usuário (o mesmo `<home>` dos locks), nunca para o sistema, e sem mexer no PATH do usuário. A Forja põe essa pasta na frente do PATH dos processos que ela mesma lança. Ferramenta já presente no PATH e na versão aceita continua valendo; a Forja só instala o que falta ou está abaixo da versão mínima.
3. **Versões fixadas e verificadas.** Um manifesto de dados da Forja lista, por ferramenta e por plataforma, a versão fixada, a origem oficial e o checksum. A instalação só vale se o checksum conferir. Nunca `curl | sh`, nunca origem que não seja a oficial da ferramenta. Mudar a versão é um commit.
4. **Como cada ferramenta é instalada sai da leitura do passo 0**, a partir das instruções oficiais dela, e não de suposição. Instalação por pacote do ecossistema (pip, npm) ou por binário de release dependem do que cada ferramenta publica.
5. **Quando instala.** O comando `forja instalar` instala e é idempotente. O `forja` sem argumentos detecta o que falta e mostra, no resumo, o que seria instalado; a confirmação única do ADR 0017 cobre também a instalação. O `forja doctor` continua só verificando e passa a apontar `forja instalar`. Sem terminal (CI, `--config`), a Forja instala apenas se o `execucao.toml` pedir, nunca por conta própria.
6. **A Forja não apaga nada.** Como no ADR 0017 para branches, remover as ferramentas é apagar a pasta; a Forja mostra o caminho e não o remove.
7. **Instalação da Forja.** A Forja é um pacote instalável por um comando (`uv tool install`, como a mensagem do `doctor` já assume), e o resto vem do `forja instalar` no primeiro uso. Publicar o pacote em registro público é decisão do dono e não faz parte deste plano; o plano entrega o pacote construível e testado em ambiente limpo.
8. **Plataformas.** Windows e Linux (WSL). macOS suspenso por decisão do dono (02/11/2026).
9. **Rede.** A instalação precisa de rede. Sem rede, falha com mensagem clara, sem instalação parcial.
11. **pytest e coverage ficam fora.** São do interpretador do repositório alvo (`repo_python`) ou do ambiente virtual da execução (ADR 0036); o `doctor` já diz como prepará-lo.
10. **A instalação é visual.** Ordem do dono (02/11/2026): processo claro, compreensível e elaborado, com ótima interface no terminal. Cada ferramenta aparece com nome, para que serve, versão, origem, tamanho, etapa (baixando, conferindo checksum, extraindo, verificando) e resultado; um resumo final diz o que foi instalado, onde e o que falhou. Vale nas três camadas da UI existente (tela cheia, linha viva, texto simples), com os mesmos limites de largura. O instalador só emite eventos; quem desenha é a UI.

## Manifesto de ferramentas (passo 2, feito em 02/11/2026)

Código em `src\forja\toolchain\`: `manifest.py` (esquema pydantic, frozen, `extra="forbid"`), `load.py` (carregador) e `manifest.toml` (dados, dentro do pacote; o `hatchling` o inclui na wheel, como já faz com os `init_scripts` do Java). Testes em `tests\toolchain`.

**Nomes públicos do carregador:** `load_manifest(path=None)` (o manifesto embarcado, ou o de `path`), `parse_manifest(text, source)`, `find_tool(manifest, nome)`, `artifact_for(manifest, nome, plataforma=None)` (a plataforma atual por padrão), `current_platform(system=None, machine=None)`; exceções `ManifestError` (lista todos os problemas de uma vez), `UnknownTool`, `UnsupportedPlatform`, `NoArtifactForPlatform`. Esquema: `Manifest`, `Tool`, `Artifact`, `Platform` (`windows-x64`, `linux-x64`).

**O que o esquema recusa:** campo faltando ou desconhecido; URL (`url` ou `checksum_source`) que não seja `https`; checksum que não seja hexadecimal minúsculo do tamanho do algoritmo (`sha256` 64, `sha512` 128); tamanho que não seja inteiro positivo; tipo de artefato que não bata com o sufixo da URL; caminho do executável absoluto, com `..`, `\`, letra de unidade ou segmento vazio; `needed_by` que não seja `"always"` ou uma lista sem repetição de linguagens conhecidas; ferramenta repetida; plataforma fora de `windows-x64` e `linux-x64`; ferramenta sem plataforma; manifesto sem ferramentas. Nenhuma ferramenta entra sem checksum porque o campo é obrigatório.

**Campos por ferramenta:** `name`, `executable`, `purpose` (português, a UI mostra), `license` (SPDX), `version`, `needed_by`. **Por plataforma:** `url`, `kind` (`zip`, `tar.gz`, `tar.xz`, `wheel`, `binary`), `size`, `algorithm`, `checksum`, `checksum_source` (de onde o valor foi lido) e `executable_path`. `binary` foi acrescentado aos tipos do plano porque o osv-scanner publica o executável avulso (o `executable_path` é o nome com que o instalador o grava). Para `wheel`, `executable_path` é relativo ao ambiente virtual (`Scripts/semgrep.exe`, `bin/semgrep`).

**Leitura dos checksums.** Cada valor foi lido do arquivo oficial da ferramenta, e os 22 artefatos (21 arquivos distintos; o Gradle é o mesmo zip nas duas plataformas) foram **baixados e conferidos de fato**: o SHA bateu e o tamanho em bytes é o do arquivo baixado. Fonte e algoritmo:

| Ferramenta | Versão | Algoritmo | Fonte do checksum | Windows x64 | Linux x64 |
| --- | --- | --- | --- | --- | --- |
| gitleaks | 8.30.1 | sha256 | `gitleaks_8.30.1_checksums.txt` do release | zip | tar.gz |
| osv-scanner | 2.7.0 | sha256 | `osv-scanner_SHA256SUMS` do release | `.exe` avulso | binário avulso |
| jscpd | 5.4.2 | sha256 | `checksums.txt` do release | tar.gz `windows-x64-msvc` | tar.gz `linux-x64-gnu` (glibc, serve no WSL) |
| semgrep | 1.183.0 | sha256 | JSON do PyPI (`/pypi/semgrep/1.183.0/json`) | wheel `win_amd64` | wheel `manylinux_2_34_x86_64` |
| go | 1.27.3 | sha256 | `go.dev/dl/?mode=json&include=all` | zip | tar.gz |
| golangci-lint | 2.15.0 | sha256 | `golangci-lint-2.15.0-checksums.txt` | zip | tar.gz |
| node | 26.13.0 | sha256 | `SHASUMS256.txt` | zip | tar.xz |
| dotnet-sdk | 10.0.403 | sha512 | `releases.json` do canal 10.0 (campo `hash`) | zip | tar.gz |
| jdk (Temurin) | 21.0.13+9 | sha256 | `.sha256.txt` do release no GitHub da Adoptium, igual ao campo `checksum` da API da Adoptium | zip | tar.gz |
| maven | 3.10.0 | sha512 | `.sha512` ao lado do arquivo | zip | tar.gz |
| gradle | 9.8.2 | sha256 | `.sha256` ao lado do arquivo (igual ao campo `checksum` de `services.gradle.org/versions/all`) | zip `bin` | o mesmo zip |

No GitHub, os checksums dos arquivos de release coincidem também com o campo `digest` da API de releases.

**Resolvido do que estava em aberto:**

- **Algoritmo de gitleaks e jscpd:** sha256, nos dois (arquivo de checksums do release). golangci-lint, osv-scanner, Go, Node e Gradle também sha256; dotnet e Maven, sha512.
- **Escolha do artefato:** Windows x64 e Linux x64 (a Forja no WSL é Linux glibc). jscpd: `msvc` no Windows e `gnu` no Linux, nunca `musl`. Node no Linux: `tar.xz` (menor). Maven no Linux: `tar.gz`, que guarda o bit de execução; o Gradle só publica zip, então o instalador (passo 3) tem de marcar o executável no Linux.
- **npm dentro do pacote do Node:** sim, nas duas plataformas (`npm`, `npm.cmd` na raiz do zip; `bin/npm` no tar). Nada a instalar à parte.
- **Go sem administrador:** o Go publica o zip e o tar.gz (pasta `go/` com `bin\go.exe` e `gofmt.exe`); é extrair numa pasta da Forja. O passo 3 faz isso.
- **Semgrep no Windows nativo:** o PyPI tem a wheel `win_amd64` da 1.183.0 (traz `semgrep-core.exe`). Que ela funcione na prática só o passo 3 e o E2E mostram. **Limite:** o checksum fixa só a wheel do semgrep; as cerca de 28 dependências dela (`Requires-Dist`) o `pip` resolve no PyPI sem checksum do manifesto. O passo 3 decide como tratá-las (por exemplo `pip install` com arquivo de requisitos com hashes), sem fugir da decisão 3.
- **Licenças** (SPDX, lidas do PyPI ou da API do GitHub): a do semgrep é `LGPL-2.1-or-later` (PyPI), a do golangci-lint `GPL-3.0` (como o GitHub a declara), o JDK `GPL-2.0-only WITH Classpath-exception-2.0`. O Maven é Apache-2.0 (GitHub declara), o que fecha a dúvida do passo 0.
- **JDK 21.** Escolhido o LTS 21 (21.0.13+9, o mais recente da série 21 na API da Adoptium em 02/11/2026): o template Maven da Forja usa `release` 17 e os testes do projeto passam com o 21; o 21 cobre o `release` 17 e é aceito pelo Gradle 9.8.2 (JVM 17 a 27).

**Fora do manifesto:** nenhuma das onze ficou de fora; todas tiveram checksum lido de fonte oficial e conferido. Assinaturas (PGP, sigstore, SLSA) não são verificadas: a decisão 3 pede o checksum.

## Instalador (passo 3, feito em 02/11/2026)

Código em `src\forja\toolchain\install.py`. Nomes públicos: `install_tool(manifest, nome, raiz, *, target=None, fetch=https_fetch, python=sys.executable)` (assíncrona; devolve `Installed(tool, version, directory, executable, already)`), `tools_dir()` (`<home>\tools`, onde a Forja guarda as ferramentas), `https_fetch`, `InstallError(tool, url, reason)` e `MARKER` (`.forja-installed`). `fetch` é injetável: os testes usam origem falsa, sem rede. O passo 3 não emite eventos; o passo 6 liga o instalador aos eventos do passo 5.

- **Onde:** `<raiz>\<ferramenta>\<versão>\`. Versões diferentes ficam lado a lado; nada fora da pasta, nada no PATH.
- **Ordem:** baixa para uma pasta temporária, confere **tamanho** e **checksum** do manifesto (`sha256` ou `sha512`) e só então desempacota. Arquivo que não confere não é aberto.
- **Desempacotar:** zip recusa entrada que cairia fora da pasta; tar usa `filter="data"` (recusa caminho e link que escapam); `binary` é copiado para o `executable_path`; `wheel` ganha ambiente virtual próprio, feito no lugar final (os scripts do ambiente guardam o caminho dele) com `pip install` da wheel. No Linux o executável recebe o bit de execução (o zip do Gradle não o guarda).
- **Sem instalação parcial:** o `MARKER` (versão e checksum) é escrito por último. Pasta sem marcador, com marcador de outro checksum ou sem o executável conta como não instalada e é refeita; qualquer falha apaga o que foi feito e levanta `InstallError` com ferramenta, origem e motivo (rede, tamanho, checksum, desempacotar, executável ausente, `pip`).
- **Idempotente:** marcador igual e executável presente: devolve `already=True`, sem baixar.
- **Limite aberto (dono):** as dependências do semgrep (cerca de 28) o `pip` resolve no PyPI sem checksum do manifesto, como já dito no passo 2. A wheel do semgrep é verificada; o que ela puxa, não. Resolver exigiria um arquivo de requisitos com hashes por plataforma, dado novo no manifesto; não foi acrescentado sem ordem.
- **Não feito aqui:** instalar apenas as ferramentas de uma linguagem (passo 7), PATH dos processos lançados e `doctor` (passo 4), comando `forja instalar` e eventos (passo 6), gate de mutação (passo 9).

## Passos (um commit cada)

0. **Feito (02/11):** **Ler o que falta, por inteiro:** para cada ferramenta da lista, a instrução oficial de instalação, a licença, como publica checksum ou assinatura, as plataformas suportadas e as versões mínimas que a Forja usa. Escrever o resultado aqui e corrigir as decisões que divergirem, em especial as 1 e 4.
1. **ADR** que substitui a parte do ADR 0017 sobre instalação; atualizar `docs\adr\README.md` e `docs\estado.md`.
2. **Feito (02/11):** **Manifesto de ferramentas** (dados): versão fixada, origem, checksum por plataforma, linguagem que exige a ferramenta. Testes do esquema. Ver "Manifesto de ferramentas" acima.
3. **Feito (02/11):** **Instalador:** baixar, conferir o checksum, extrair na pasta da Forja, idempotente, sem instalação parcial. Testes sem rede, com origem falsa. Ver "Instalador" abaixo.
4. **Feito (02/11):** **Resolução** (`toolchain\resolve.py`; ferramenta de `wheel` vai no fim do PATH, para o `python` do ambiente dela não esconder o do repositório): a pasta da Forja entra na frente do PATH dos processos lançados; o `doctor` diz quando a ferramenta é a instalada pela Forja.
5. **Feito (02/11):** **Interface visual da instalação (decisão 10):** modelo de eventos da instalação e as três camadas da UI desenhando-os, testadas sem terminal e sem rede com fluxos de eventos falsos. Independe do instalador real.
6. **Feito (02/11):** **Comando `forja instalar`** e a oferta dentro do `forja` guia (resumo e confirmação única), regra de CI da decisão 5, instalador emitindo os eventos do passo 5, mensagens `fix` do `doctor` apontando `forja instalar`.
7. **Ferramentas por linguagem** (go, golangci-lint, node, SDK dotnet, JDK, Maven ou Gradle), instaladas só para as linguagens detectadas.
8. **Instalação da Forja:** pacote construível, instalado em ambiente limpo e exercitado com `forja instalar` e `forja doctor`; documentação do usuário (instalar, atualizar, onde ficam as ferramentas, como removê-las).
9. **Gate de mutação** nos arquivos novos (`scripts\mutate.py`).
10. **Ponta a ponta** em máquina limpa, no fecho (regra do dono: testes reais só no E2E final): instalar a Forja, `forja instalar` e uma execução, no Windows e no Linux via WSL.

## Limites já conhecidos

- Toolchains grandes (JDK, SDK dotnet) pesam em disco e em tempo de download; por isso só vêm para a linguagem detectada.
- Rede corporativa, proxy e antivírus podem barrar download ou execução de binário; a falha tem de dizer qual ferramenta, qual origem e o que aconteceu.
- A fila 13 (`jscpd`) vem antes na Fila; o `jscpd` entra no manifesto deste plano como as demais.
