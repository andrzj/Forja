# Plano: gate 10, segurança e dependências

Estado: plano, nada implementado. Ordem decidida com o dono (22/10): gates grandes só com plano escrito antes; este vem primeiro por ser o de maior risco para quem entrega.

## O que a Especificação diz

- Tabela de gates, linha 10: reprova com **achado novo do Semgrep**; **vulnerabilidade ou licença proibida** em dependência; **dependência nova inexistente ou suspeita** no registro oficial.
- Seção "O que o agente produz": SAST com Semgrep, regras para as seis linguagens; dependências com OSV-Scanner (vulnerabilidades) e checagem de licença; dependência nova precisa existir no registro oficial, com idade e uso verificados, e **dispara ADR**.
- Plano de execução, incremento 5: "segurança completa (Semgrep, OSV-Scanner, licenças, verificação de dependência nova)".
- Regras gerais que valem aqui: catraca (só o novo reprova), configuração do repositório prevalece sobre o perfil padrão, check novo nasce em modo observação, ferramenta que falha é `Inconclusive`, nunca aprovação.

## O que as ferramentas fazem (documentação oficial lida em 22/10)

- **Semgrep** (`docs.semgrep.dev/cli-reference`): `--config` aceita arquivo ou diretório local de regras; `p/...` e `auto` vão ao registro (e `--metrics=off`, `--disable-version-check` evitam chamadas). `--json --json-output=<arquivo>`. Códigos: 0 ok (com `--error`, 1 se há achado), 2 erro fatal, 3, 4, 5, 7, 8, 13 para erros específicos. `--baseline-commit` aborta fora de git, com mudanças não commitadas ou commit inexistente: **não serve**, porque o diff da tentativa está no working tree. A documentação não garante execução totalmente offline.
- **OSV-Scanner** (`google.github.io/osv-scanner`): `osv-scanner scan -r <dir>` ou `-L <lockfile>`; `--format json --output-file`; `--licenses` resume licenças e `--licenses="MIT,Apache-2.0"` (lista **permitida**) reporta violações; `--offline-vulnerabilities` usa bases baixadas. Saída JSON: `results[].source.path`, `results[].packages[].package{name,version,ecosystem}`, `.vulnerabilities[].id`, `.groups[]`. Códigos: 0 sem achado, 1 com achado, 127 erro geral, 128 nenhum pacote encontrado, 129 a 255 erros. **Não lido ainda:** os nomes dos campos de licença no JSON e a lista de manifestos/lockfiles suportados (páginas "License Scanning" e "Supported Artifacts").

## Decisões

1. **Três checks, um gate.** `sast`, `dependency_audit` (vulnerabilidades e licenças) e `new_dependency`, todos `gate = 10`, cada um com o seu modo (ADR 0003). Nascem em observação.
2. **Semgrep e OSV-Scanner são transversais**, como o gitleaks e o lizard: não viram operação de adaptador. O comando entra no `PipelineMeasurer` como parâmetro (`semgrep=`, `osv_scanner=`), é achado pela sessão e listado no `doctor`.
3. **Catraca no SAST.** Sem `--baseline-commit`: roda nos arquivos mudados no estado novo e no texto do commit pai, na cópia privada que o `LintCheck._before` já faz (`checks/layout.py`), e compara contagem por (arquivo, regra). Se roda no novo e não no antigo: `Inconclusive`.
4. **Regras do Semgrep: só locais.** Regras do repositório (`.semgrep/` ou `.semgrep.yml`) prevalecem; sem elas, um diretório de regras que a Forja distribui. Nunca `auto` nem `p/...`, sempre `--metrics=off --disable-version-check`.
5. **Auditoria de dependências só quando algo mudou.** Se nenhum manifesto ou lockfile está entre os arquivos mudados, `Approved` sem rodar. Senão, `osv-scanner` no estado novo e no estado antigo (lockfiles do commit pai escritos numa cópia); reprova o par (pacote, versão, vulnerabilidade) que existe só no novo. Código 128 vale como "nada a auditar".
6. **Licença proibida é lista da política.** O OSV-Scanner só tem lista permitida; a política da Forja guarda a lista de **proibidas** (a Especificação diz "licença proibida") e o check compara com as licenças que o JSON traz. Fica `Inconclusive` se o pacote não traz licença.
7. **Dependência nova** (inexistente ou suspeita): cada adaptador declara quais arquivos são manifesto e como extrair os nomes adicionados (capacidade opcional, como `owns_test`); o check consulta o registro oficial do ecossistema (existência, idade, uso). Registro inacessível: `Inconclusive`. O "dispara ADR" é do papel documentador (incremento 4) e **não** entra aqui: este check só reprova ou registra o achado.
8. **Rede.** Os checks 2 e 3 precisam de rede (OSV e registros). Modo offline do OSV só com bases já baixadas, e isso fica fora deste plano.

## Passos (um commit cada)

0. **Ler o que falta:** páginas "License Scanning" e "Supported Artifacts and Manifests" do OSV-Scanner; esquema do JSON do Semgrep; linguagens suportadas pelo Semgrep. Corrigir este plano se algo divergir.
1. **`sast`:** parser do JSON do Semgrep, check com a catraca da decisão 3, parâmetro `semgrep=` no measurer, `doctor`. Testes com ferramenta falsa (molde: `FAKE_GITLEAKS`).
2. **Regras distribuídas:** o diretório padrão de regras e como a Forja o localiza. Depende da pergunta aberta abaixo.
3. **`dependency_audit`:** parser do JSON do OSV (vulnerabilidades e licenças), comparação novo contra antigo, política de licenças proibidas, parâmetro `osv_scanner=`.
4. **`new_dependency`:** capacidade opcional nos cinco adaptadores (extrair nomes adicionados dos manifestos), consulta aos registros (npm, PyPI, proxy do Go, Maven Central, NuGet), idade e uso.
5. **Integração:** registro dos três no `PipelineMeasurer.judge` depois de `module_depth`, configuração em `execucao.toml`, resumo.
6. **Ponta a ponta** com as ferramentas reais, no fecho (regra do dono: testes reais só no E2E final). Gate de mutação no WSL nos arquivos novos.

## Pergunta aberta (a Especificação não responde)

Quais regras do Semgrep a Forja distribui para as seis linguagens quando o repositório não tem as suas? Opções: escrever e manter um conjunto próprio e pequeno (controle total, trabalho nosso) ou fixar uma cópia versionada de regras públicas (menos trabalho, licença das regras a conferir). Precisa de decisão antes do passo 2.

## Limites já conhecidos

- A documentação do Semgrep não garante execução 100% offline; só se verifica na prática.
- Sem rede, `dependency_audit` e `new_dependency` ficam `Inconclusive` (política do gate decide).
- Dependência transitiva nova (que entra só pelo lockfile) é pega pelo OSV, mas não por `new_dependency`, que olha só os manifestos.
