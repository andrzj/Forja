# Instalar a Forja

A Forja é um pacote Python (3.12 ou mais) que instala o comando `forja`. As ferramentas de terceiros de que ela depende (gitleaks, osv-scanner, jscpd, Semgrep e as de cada linguagem) a própria Forja instala, com `forja instalar`. Decisão e limites: ADR 0037 e `docs\plano-instalacao.md`.

## Pré-requisitos

- **uv** (instala a Forja e o Python 3.12 que ela exige).
- **git**: a Forja não o instala; o `forja doctor` o verifica.
- **A CLI do agente** (por exemplo o Claude Code), com o seu login. A Forja não instala a CLI nem faz o login.
- Rede, na instalação das ferramentas. Sem rede a instalação falha com mensagem clara e não deixa instalação pela metade.
- Windows ou Linux (WSL). macOS está suspenso.

## Instalar

O pacote ainda não está publicado em registro. A partir de uma cópia do repositório:

```bash
uv tool install .
```

Isso põe o comando `forja` no PATH do uv. Para checar:

```bash
forja doctor
```

O `doctor` só verifica e diz o que falta; ele não instala nada.

## Instalar as ferramentas externas

```bash
forja instalar
```

Instala as ferramentas que faltam e mostra o andamento (nome, para que serve, versão, etapa e resultado de cada uma), com um resumo no fim. Rodar de novo não baixa o que já está instalado. Cada arquivo baixado tem o tamanho e o checksum conferidos contra o manifesto da Forja antes de ser aberto.

- Ferramentas de todas as execuções: gitleaks, osv-scanner, jscpd e Semgrep.
- Ferramentas por linguagem (Go, golangci-lint, Node, SDK do .NET, JDK, Maven, Gradle): só para as linguagens detectadas no repositório. Rode `forja instalar` dentro do repositório alvo.
- Uma ferramenta que já está no PATH vale e não é instalada de novo.

Quem roda só `forja` (o guia) vê, no resumo, o que faltaria instalar, e a confirmação única cobre a instalação. Sem terminal (CI) ou com `--config`, a Forja só instala se o `execucao.toml` tiver `instalar_ferramentas = true`.

## Onde ficam as ferramentas

Em `<home da Forja>\tools\<ferramenta>\<versão>\`. O `<home>` é `FORJA_HOME`, se definida; senão `%LOCALAPPDATA%\forja` no Windows e `~/.local/share/forja` no Linux. Nada é instalado fora dessa pasta, não é preciso administrador e o PATH do usuário não muda: a Forja só põe essa pasta na frente do PATH dos processos que ela mesma lança. O `forja doctor` diz quando uma ferramenta é a instalada pela Forja.

## Atualizar

A Forja:

```bash
uv tool install --reinstall .
```

As ferramentas externas têm a versão fixada no manifesto da Forja; uma versão nova da Forja traz versões novas das ferramentas, e `forja instalar` as instala ao lado das antigas.

## Remover

A Forja não apaga nada por conta própria.

- A Forja: `uv tool uninstall forja`.
- As ferramentas externas: apague a pasta `<home da Forja>\tools`.
