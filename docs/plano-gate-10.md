# Plano: gate 10, segurança e dependências

Estado: plano, nada implementado; sem perguntas abertas. Ordem decidida com o dono (22/10): gates grandes só com plano escrito antes; este vem primeiro por ser o de maior risco para quem entrega.

## O que a Especificação diz

- Tabela de gates, linha 10: reprova com **achado novo do Semgrep**; **vulnerabilidade ou licença proibida** em dependência; **dependência nova inexistente ou suspeita** no registro oficial.
- Seção "O que o agente produz": SAST com Semgrep, regras para as seis linguagens; dependências com OSV-Scanner (vulnerabilidades) e checagem de licença; dependência nova precisa existir no registro oficial, com idade e uso verificados, e **dispara ADR**.
- Plano de execução, incremento 5: "segurança completa (Semgrep, OSV-Scanner, licenças, verificação de dependência nova)".
- Regras gerais que valem aqui: catraca (só o novo reprova), configuração do repositório prevalece sobre o perfil padrão, check novo nasce em modo observação, ferramenta que falha é `Inconclusive`, nunca aprovação.

## O que as ferramentas fazem (documentação oficial lida em 22/10)

- **Semgrep** (`docs.semgrep.dev/cli-reference`): `--config` aceita arquivo ou diretório local de regras; `p/...` e `auto` vão ao registro (e `--metrics=off`, `--disable-version-check` evitam chamadas). `--json --json-output=<arquivo>`. Códigos: 0 ok (com `--error`, 1 se há achado), 2 erro fatal, 3, 4, 5, 7, 8, 13 para erros específicos. `--baseline-commit` aborta fora de git, com mudanças não commitadas ou commit inexistente: **não serve**, porque o diff da tentativa está no working tree. A documentação não garante execução totalmente offline.
- **OSV-Scanner** (`google.github.io/osv-scanner`): `osv-scanner scan -r <dir>` ou `-L <lockfile>`; `--format json --output-file`; `--licenses` resume licenças e `--licenses="MIT,Apache-2.0"` (lista **permitida**) reporta violações; `--offline-vulnerabilities` usa bases baixadas. Saída JSON: `results[].source.path`, `results[].packages[].package{name,version,ecosystem}`, `.vulnerabilities[].id`, `.groups[]`. Códigos: 0 sem achado, 1 com achado, 127 erro geral, 128 nenhum pacote encontrado, 129 a 255 erros. **Não lido ainda:** os nomes dos campos de licença no JSON e a lista de manifestos/lockfiles suportados (páginas "License Scanning" e "Supported Artifacts").

### Leitura do passo 0 (22/10, feito)

- **OSV, licenças:** `--licenses` resume; `--licenses="A,B"` é lista permitida (SPDX); dados vêm da API deps.dev (rede). JSON (código-fonte `pkg/models/results.go`, a página de saída não documenta): `results[].packages[].licenses[]` e `.license_violations[]` (strings SPDX), `license_summary[]` com `{name,count}` no nível raiz. Como pacote sem licença aparece: **não documentado**, verificar no E2E; até lá, `licenses` vazio = `Inconclusive` para aquele pacote.
- **OSV, artefatos suportados:** Python `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pdm.lock`, `uv.lock`; JS/TS **só lockfiles** (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`), **`package.json` não é lido**; Go `go.mod`; Java `pom.xml`, `gradle.lockfile`; C# `packages.lock.json`, `packages.config`, `deps.json`. Versões vindas de manifesto sem trava são aproximadas.
- **Semgrep, linguagens:** as seis são GA.
- **Semgrep, JSON** (`semgrep_output_v1.atd`): raiz `results[]` e `errors[]`; cada resultado `check_id`, `path`, `start{line,col,offset}`, `end`, `extra{message,severity,fingerprint,lines,metadata}`; `severity` em `ERROR|WARNING|INFO|...`; erro com `code`, `level`, `type`, `path`, `message`.
- **Semgrep, não documentado:** comportamento com `--config` apontando para diretório sem regras; código 7 aparece como "regra inválida" e como "configuração ausente". Tratar qualquer código fora de 0/1 como `Inconclusive` e checar no E2E.

### Correções às decisões abaixo

- Decisão 5: a lista de "manifestos e lockfiles" que dispara a auditoria é a lista de artefatos acima. `package.json` mudado sem lockfile mudado **não** dispara o OSV (ele não o lê); isso é coberto por `new_dependency`.
- Decisão 7: `package.json` entra como manifesto de `new_dependency` mesmo o OSV não lendo.

## Decisões

1. **Três checks, um gate.** `sast`, `dependency_audit` (vulnerabilidades e licenças) e `new_dependency`, todos `gate = 10`, cada um com o seu modo (ADR 0003). Nascem em observação.
2. **Semgrep e OSV-Scanner são transversais**, como o gitleaks e o lizard: não viram operação de adaptador. O comando entra no `PipelineMeasurer` como parâmetro (`semgrep=`, `osv_scanner=`), é achado pela sessão e listado no `doctor`.
3. **Catraca no SAST.** Sem `--baseline-commit`: roda nos arquivos mudados no estado novo e no texto do commit pai, na cópia privada que o `LintCheck._before` já faz (`checks/layout.py`), e compara contagem por (arquivo, regra). Se roda no novo e não no antigo: `Inconclusive`.
4. **Regras do Semgrep: o usuário fornece, a Forja não tem padrão** (decisão do dono, 22/10; ADR 0024). A configuração é um arquivo ou diretório local, dado por `--semgrep-config` ou pelo `execucao.toml`; senão `.semgrep.yml` ou `.semgrep/` na raiz do commit base. **Sem configuração o check `sast` não executa**: devolve `NotApplicable`, nunca `Approved`, e o resumo da preparação e o da entrega dizem em destaque "SAST não executado: sem configuração". Referências de registro (`auto`, `p/...`, URL) são recusadas com erro de configuração (código 2); sempre `--metrics=off --disable-version-check`. O `--help` e a documentação dizem que o usuário deve fornecer a configuração.
4b. **As regras não vêm da worktree da tentativa.** São lidas do commit base (ou de uma cópia feita na preparação, fora da worktree), para que o agente não as edite e silencie achados. Alterar o arquivo de regras numa tentativa é alteração protegida pelo gate de escopo.
5. **Auditoria de dependências só quando algo mudou.** Se nenhum manifesto ou lockfile está entre os arquivos mudados, `Approved` sem rodar. Senão, `osv-scanner` no estado novo e no estado antigo (lockfiles do commit pai escritos numa cópia); reprova o par (pacote, versão, vulnerabilidade) que existe só no novo. Código 128 vale como "nada a auditar".
6. **Licença proibida é lista da política, sem padrão.** O OSV-Scanner só tem lista permitida; a política da Forja guarda a lista de **proibidas** (a Especificação diz "licença proibida") e o check compara com as licenças que o JSON traz. Mesmo princípio do Semgrep: sem lista fornecida, a parte de licenças não executa (`NotApplicable`, dito no resumo); as vulnerabilidades do OSV não precisam de configuração e rodam sempre. Fica `Inconclusive` se o pacote não traz licença.
7. **Dependência nova** (inexistente ou suspeita): cada adaptador declara quais arquivos são manifesto e como extrair os nomes adicionados (capacidade opcional, como `owns_test`); o check consulta o registro oficial do ecossistema (existência, idade, uso). Registro inacessível: `Inconclusive`. O "dispara ADR" é do papel documentador (incremento 4) e **não** entra aqui: este check só reprova ou registra o achado.
8. **Rede.** Os checks 2 e 3 precisam de rede (OSV e registros). Modo offline do OSV só com bases já baixadas, e isso fica fora deste plano.

## Passos (um commit cada)

0. **Feito (22/10):** **Ler o que falta:** páginas "License Scanning" e "Supported Artifacts and Manifests" do OSV-Scanner; esquema do JSON do Semgrep; linguagens suportadas pelo Semgrep. Corrigir este plano se algo divergir.
1. **`sast`:** parser do JSON do Semgrep, check com a catraca da decisão 3, parâmetro `semgrep=` no measurer. Testes com ferramenta falsa (molde: `FAKE_GITLEAKS`).
2. **Configuração do Semgrep (decisões 4 e 4b):** `--semgrep-config` e chave do `execucao.toml`, descoberta de `.semgrep.yml`/`.semgrep/` no commit base, recusa de referência de registro, `NotApplicable` sem configuração, linha no resumo da preparação e da entrega, texto do `--help`, `doctor` (pede o `semgrep` só quando há configuração), proteção do arquivo de regras no gate de escopo.
3. **`dependency_audit`:** parser do JSON do OSV (vulnerabilidades e licenças), comparação novo contra antigo, lista de licenças proibidas da política (sem padrão), parâmetro `osv_scanner=`.
4. **`new_dependency`:** capacidade opcional nos cinco adaptadores (extrair nomes adicionados dos manifestos), consulta aos registros (npm, PyPI, proxy do Go, Maven Central, NuGet), idade e uso.
5. **Integração:** registro dos três no `PipelineMeasurer.judge` depois de `module_depth`, configuração em `execucao.toml`, resumo.
6. **Documentação do usuário:** a documentação diz que o SAST e a checagem de licenças dependem de configuração fornecida, aponta para a documentação do Semgrep e traz um exemplo mínimo que a Forja nunca usa sozinha (fica para o incremento 4/7, junto com a documentação de uso).
7. **Ponta a ponta** com as ferramentas reais, no fecho (regra do dono: testes reais só no E2E final). Gate de mutação no WSL nos arquivos novos.

## Decidido pelo dono (22/10)

A Forja não distribui regras do Semgrep nem lista de licenças: o usuário fornece a configuração, e sem ela o check não executa. Registrado no ADR 0024, que também emenda a linha de SAST da Especificação.

## Limites já conhecidos

- A documentação do Semgrep não garante execução 100% offline; só se verifica na prática.
- Sem rede, `dependency_audit` e `new_dependency` ficam `Inconclusive` (política do gate decide).
- Dependência transitiva nova (que entra só pelo lockfile) é pega pelo OSV, mas não por `new_dependency`, que olha só os manifestos.
