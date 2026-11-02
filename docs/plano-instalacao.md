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
- **Por linguagem do repositório alvo:** Python: pytest, coverage. Go: go, golangci-lint. TypeScript/JavaScript: node, npm, vitest ou jest, eslint, tsc, prettier, cobertura Istanbul/c8. C#: SDK dotnet, coverlet. Java: JDK, Maven ou Gradle, JaCoCo, Checkstyle.

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
10. **A instalação é visual.** Ordem do dono (02/11/2026): processo claro, compreensível e elaborado, com ótima interface no terminal. Cada ferramenta aparece com nome, para que serve, versão, origem, tamanho, etapa (baixando, conferindo checksum, extraindo, verificando) e resultado; um resumo final diz o que foi instalado, onde e o que falhou. Vale nas três camadas da UI existente (tela cheia, linha viva, texto simples), com os mesmos limites de largura. O instalador só emite eventos; quem desenha é a UI.

## Passos (um commit cada)

0. **Ler o que falta, por inteiro:** para cada ferramenta da lista, a instrução oficial de instalação, a licença, como publica checksum ou assinatura, as plataformas suportadas e as versões mínimas que a Forja usa. Escrever o resultado aqui e corrigir as decisões que divergirem, em especial as 1 e 4.
1. **ADR** que substitui a parte do ADR 0017 sobre instalação; atualizar `docs\adr\README.md` e `docs\estado.md`.
2. **Manifesto de ferramentas** (dados): versão fixada, origem, checksum por plataforma, linguagem que exige a ferramenta. Testes do esquema.
3. **Instalador:** baixar, conferir o checksum, extrair na pasta da Forja, idempotente, sem instalação parcial. Testes sem rede, com origem falsa.
4. **Resolução:** a pasta da Forja entra na frente do PATH dos processos lançados; o `doctor` diz quando a ferramenta é a instalada pela Forja.
5. **Interface visual da instalação (decisão 10):** modelo de eventos da instalação e as três camadas da UI desenhando-os, testadas sem terminal e sem rede com fluxos de eventos falsos. Independe do instalador real.
6. **Comando `forja instalar`** e a oferta dentro do `forja` guia (resumo e confirmação única), regra de CI da decisão 5, instalador emitindo os eventos do passo 5, mensagens `fix` do `doctor` apontando `forja instalar`.
7. **Ferramentas por linguagem** (go, node, dotnet, JDK, Maven ou Gradle e as demais da lista), instaladas só para as linguagens detectadas.
8. **Instalação da Forja:** pacote construível, instalado em ambiente limpo e exercitado com `forja instalar` e `forja doctor`; documentação do usuário (instalar, atualizar, onde ficam as ferramentas, como removê-las).
9. **Gate de mutação** nos arquivos novos (`scripts\mutate.py`).
10. **Ponta a ponta** em máquina limpa, no fecho (regra do dono: testes reais só no E2E final): instalar a Forja, `forja instalar` e uma execução, no Windows e no Linux via WSL.

## Limites já conhecidos

- Toolchains grandes (JDK, SDK dotnet) pesam em disco e em tempo de download; por isso só vêm para a linguagem detectada.
- Rede corporativa, proxy e antivírus podem barrar download ou execução de binário; a falha tem de dizer qual ferramenta, qual origem e o que aconteceu.
- A fila 13 (`jscpd`) vem antes na Fila; o `jscpd` entra no manifesto deste plano como as demais.
