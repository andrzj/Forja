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

**Em aberto para os passos 2 e 3:** npm dentro do pacote do Node; extração do Go sem administrador; semgrep em Windows nativo; algoritmo dos checksums de gitleaks e jscpd; o Python do semgrep sai do Python da própria Forja (3.12, acima do mínimo 3.10 do semgrep), em ambiente virtual próprio na pasta da Forja; Checkstyle e licença do Maven sem confirmação (fora do manifesto, não afeta).

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

## Passos (um commit cada)

0. **Feito (02/11):** **Ler o que falta, por inteiro:** para cada ferramenta da lista, a instrução oficial de instalação, a licença, como publica checksum ou assinatura, as plataformas suportadas e as versões mínimas que a Forja usa. Escrever o resultado aqui e corrigir as decisões que divergirem, em especial as 1 e 4.
1. **ADR** que substitui a parte do ADR 0017 sobre instalação; atualizar `docs\adr\README.md` e `docs\estado.md`.
2. **Manifesto de ferramentas** (dados): versão fixada, origem, checksum por plataforma, linguagem que exige a ferramenta. Testes do esquema.
3. **Instalador:** baixar, conferir o checksum, extrair na pasta da Forja, idempotente, sem instalação parcial. Testes sem rede, com origem falsa.
4. **Resolução:** a pasta da Forja entra na frente do PATH dos processos lançados; o `doctor` diz quando a ferramenta é a instalada pela Forja.
5. **Interface visual da instalação (decisão 10):** modelo de eventos da instalação e as três camadas da UI desenhando-os, testadas sem terminal e sem rede com fluxos de eventos falsos. Independe do instalador real.
6. **Comando `forja instalar`** e a oferta dentro do `forja` guia (resumo e confirmação única), regra de CI da decisão 5, instalador emitindo os eventos do passo 5, mensagens `fix` do `doctor` apontando `forja instalar`.
7. **Ferramentas por linguagem** (go, golangci-lint, node, SDK dotnet, JDK, Maven ou Gradle), instaladas só para as linguagens detectadas.
8. **Instalação da Forja:** pacote construível, instalado em ambiente limpo e exercitado com `forja instalar` e `forja doctor`; documentação do usuário (instalar, atualizar, onde ficam as ferramentas, como removê-las).
9. **Gate de mutação** nos arquivos novos (`scripts\mutate.py`).
10. **Ponta a ponta** em máquina limpa, no fecho (regra do dono: testes reais só no E2E final): instalar a Forja, `forja instalar` e uma execução, no Windows e no Linux via WSL.

## Limites já conhecidos

- Toolchains grandes (JDK, SDK dotnet) pesam em disco e em tempo de download; por isso só vêm para a linguagem detectada.
- Rede corporativa, proxy e antivírus podem barrar download ou execução de binário; a falha tem de dizer qual ferramenta, qual origem e o que aconteceu.
- A fila 13 (`jscpd`) vem antes na Fila; o `jscpd` entra no manifesto deste plano como as demais.
