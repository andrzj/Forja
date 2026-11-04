# Plano: gate de duplicação (DRY)

Estado: plano, nada implementado. Origem: o dono apontou em 02/11/2026 que a duplicação (DRY) é vital e que o `jscpd`, previsto na Especificação, não foi implementado. Conferido em 02/11/2026: não há check de duplicação em `src\forja\checks` nem menção a `jscpd` no código; a Fila e o Registro não o dispensaram.

## O que a Especificação diz

- Linha 16 (políticas como código): cada predicado da biblioteca de engenharia, DRY entre eles, é um objeto com racional, fragmento de prompt, detector, limiar e métrica oposta; o texto que orienta o LLM e a regra que o julga vêm da mesma fonte.
- Linha 400 (camadas transversais às seis linguagens): **jscpd** (duplicação), ao lado de lizard, tree-sitter, Semgrep, OSV-Scanner e gitleaks.
- A tabela de gates não tem linha para duplicação. O gate 8 (métricas estruturais: CRAP ou complexidade acima do limiar, métrica oposta que piorou) é o vizinho natural; ver decisão 1.
- Regras gerais que valem aqui (as mesmas do `plano-gate-10.md`): catraca (só o novo reprova), configuração do repositório prevalece sobre o perfil padrão, check novo nasce em modo observação, ferramenta que falha é `Inconclusive`, nunca aprovação.

## O que a ferramenta faz

Leitura do passo 0 feita em 03/11/2026 (versão 5.4.2, branch `master` de `github.com/kucherenko/jscpd`). Páginas lidas: README, `jscpd.dev` (início, instalação, referência de CLI, arquivo de configuração, códigos de saída, relatores, relator JSON, migração, changelog), `FORMATS.md`, `docs\rust.md`, guias de baseline e de CI, `docs\ci-and-hooks.md` e "como a detecção funciona". **Não lido por inteiro:** os últimos ~18k caracteres de `docs\rust.md` (internos de código morto, API Rust, tabela de migração da v4; nada que o gate use) e o fim do changelog (versões anteriores à 5.2). Leitura feita por busca de páginas, não byte a byte.

Fatos que o plano usa:

- **Binário nativo (Rust), sem runtime.** Node só para o lançador npm; o binário do release não precisa. Git só para `--changed`, `--changed-only`, `--history`, `--blame` e `--baseline-from-ref`.
- **Chamada:** `jscpd [OPÇÕES] [CAMINHO]...`. `-r json` grava `<saída>\jscpd-report.json` (`-o` escolhe a pasta, `--report-name` o nome). O que `--silent` faz junto de `-r json` não está documentado.
- **Padrões:** `minTokens` 50, `minLines` 5, `mode` `mild`, `--max-lines` sem teto; `--max-size`: a página de CLI diz 1mb, `rust.md` diz sem limite (divergência não resolvida, irrelevante para código-fonte comum). Por padrão só acha clones `exact`; `renamed`, `similar` (gap, ast) e `semantic` só ligam com flag própria.
- **Códigos de saída:** 0 se nenhuma porta disparou (achar clone não falha); 1 se `--threshold` estourado, `--fail-on-new-clones` estourado, `--fail-on-empty` sem arquivo analisado, relator que não grava, caminho inexistente, `--format` desconhecido ou `--config` ilegível; N com `--exit-code N` e ao menos um clone; 2 para erro de linha de comando. Relatórios saem antes das portas.
- **Esquema do JSON:** `duplicates[]` com `format`, `kind` (`exact`/`renamed`/`similar`/`semantic`), `method` e `similarity` opcionais, `isNew` (verdadeiro quando o hash falta no baseline; falso sem baseline), `lines`, `tokens`, `firstFile` e `secondFile` (`name`, `start`, `end`, `startLoc`/`endLoc` com `line`, `column`, `position`; `blame` só com `--blame`), `fragment`; `statistics` com `detectionDate`, `formats` (por formato) e `total` (`sources`, `lines`, `tokens`, `clones`, `duplicatedLines`, `duplicatedTokens`, `percentage`, `percentageTokens`, `newClones`, `newDuplicatedLines`). Nomes relativos ao diretório varrido, com barra normal no Windows desde a 5.3.0.
- **Baseline do próprio jscpd:** arquivo JSON `{"version": 1, "fingerprints": {"<hash>": <contagem>}}`. O hash é do conteúdo do fragmento duplicado, sem caminho nem número de linha: mover arquivo, deslocar linhas ou trocar fim de linha não muda a identidade; uma cópia a mais do que o baseline permite é nova. Baseline e execução precisam das mesmas opções. `--baseline <arquivo>` + `--fail-on-new-clones [N]`; `--update-baseline`; `--baseline-from-ref <ref>` varre a árvore do ref numa worktree destacada temporária (o ref precisa existir localmente) e compara em memória, sem gravar arquivo; `--changed` só mostra clones com fragmento em arquivo que o `git status` lista (e grava `.jscpd-baseline.json` na raiz).
- **Linguagens:** 224 formatos (203 por extensão ou nome de arquivo, 21 só por `--formats-exts`/`--formats-names`); `--format` leva nomes de formato; entre eles `python`, `javascript`, `typescript`, `tsx`, `jsx`, `java`, `go`, `csharp`. `markdown`, `json`, `yaml` etc. também entram se não forem filtrados.
- **Ignorar:** `--ignore` (globs, relativos à raiz varrida), `.gitignore`, `.git\info\exclude` e `.ignore` respeitados (`--no-gitignore` desliga), links simbólicos pulados, `--ignore-pattern` (regex Rust) e regiões `jscpd:ignore-start`/`jscpd:ignore-end`.
- **Configuração:** o `jscpd` procura `.jscpd.json` no diretório de trabalho (não no caminho varrido), depois `.config\jscpd.json`, `.config\.jscpd.json`, chave `jscpd` do `package.json`; `-c` explícito vence. Chave desconhecida só avisa. Não existe `minTokens` por linguagem; só global (e por regra em `boundaries`).

**Não documentado, a resolver nos testes e no E2E:** como o `jscpd` se comporta numa worktree ligada do git ou numa cópia sem `.git` (Windows e Linux); se `--baseline-from-ref` existe desde qual versão (as chaves de baseline são de 5.1.0, `--changed` de 5.4.1; a 5.4.2 fixada cobre os dois); tratamento de barra invertida em globs no Windows.

## Decisões

1. **Um check `duplication`, `gate = 8`**, com o seu modo (ADR 0003). Nasce em **observação**. A Especificação não numera um gate para duplicação; o ADR do passo 6 registra a escolha do gate 8 e emenda a tabela.
2. **`jscpd` é transversal**, como lizard, gitleaks e Semgrep: não vira operação de adaptador. O comando entra no `PipelineMeasurer` como parâmetro (`jscpd=`), é achado pela sessão e listado no `doctor`.
3. **Catraca pelo mecanismo do próprio `jscpd`** (referência do dono, seguida como está). Só reprova a duplicação nova. A Forja roda `jscpd` com `-r json` e `--baseline-from-ref <commit pai>`; cada clone do JSON traz `isNew`, e a identidade do clone é o hash de conteúdo do `jscpd` (independe de caminho e de linha). Só conta clone `isNew` que tem fragmento em arquivo de produção alterado pela tentativa; duplicação antiga é dívida para o planejador, não motivo para recusar uma melhoria alheia. Isto substitui o desenho anterior (cópia privada à moda de `ComplexityCheck._before` e comparação de clones feita pela Forja). Se `--baseline-from-ref` não funcionar na worktree da execução (não documentado), o passo 2 cai para baseline gravado em arquivo temporário (`--baseline`), ainda com o hash do `jscpd`; o teste real fica no E2E.
4. **Limiares são os padrões do próprio `jscpd`** (`minTokens` 50, `minLines` 5, `mode` `mild`, só clones `exact`), ajustáveis no `execucao.toml` como valores globais (o `jscpd` não tem limiar por linguagem; só global e por regra de `boundaries`). Sem calibração extra (C2 foi dispensada pelo dono) e sem ligar `--ignore-identifiers`, `--similarity` etc.
5. **Raiz de testes fora da medição por padrão**, ajustável no TOML: repetição em código de teste é frequente e a regra DRY do agente é sobre produção. Usa o `test_root` do adaptador, como o resto da Forja.
6. **`jscpd` ausente, falho (código de saída diferente de 0, já que a Forja não liga nenhuma porta) ou com saída ilegível: `Inconclusive`**, nunca aprovação. Node não é requisito (confirmado no passo 0). No `doctor`, `jscpd` entra como item obrigatório, como o `gitleaks`, e a linha diz onde ficam as instruções de instalação do próprio `jscpd`. Quem instala é a fila 14 (a Forja passa a instalar as ferramentas externas OSS); até lá, o `doctor` só aponta.
7. **O texto que orienta o agente vem da mesma fonte do detector** (Especificação, linha 16): o fragmento de prompt de DRY e o limiar do check saem do mesmo objeto de política. O passo 5 olha como as instruções atuais tratam DRY (ADR 0036 trata só de dependência) e liga o fragmento ao detector.
8. **Rede:** nada. O `jscpd` lê arquivos locais.

## Passos (um commit cada)

0. **Feito (03/11):** leitura da documentação oficial do `jscpd` (ver "O que a ferramenta faz"); decisões 3, 4 e 6 corrigidas.
1. **Feito (03/11):** parser da saída do `jscpd` para um modelo de clones (`checks\duplication_report.py`). Testes com documentos JSON; a ferramenta falsa (molde: `FAKE_GITLEAKS`) entra no passo 2.
2. **Feito (03/11):** check `duplication` (`checks\duplication.py`) com a catraca da decisão 3, `gate = 8`. O modo observação (`CheckSpec`) entra com o registro, nos passos 3 e 4.
3. **Feito (03/11):** `CheckSpec` (modo observação) com os limites globais `min_tokens` e `min_lines` no `forja.toml`, descoberta do comando (`Detection.jscpd`, parâmetro `jscpd` do medidor), linha do `doctor`. A raiz de testes em `ignore` sai da classificação de testes do medidor e entra com o registro, no passo 4.
4. **Feito (03/11):** integração: registro no `PipelineMeasurer.judge` depois de `module_depth`, resumo da preparação e da entrega. Atualizar as listas de checks dos testes (`EVERY_CHECK`, `GATES`, `standard` em `tests\checks\support.py`, ordens em `test_measurer.py` e `test_precision.py`, tabela de `test_pieces.py`).
5. **Feito (03/11):** instruções ao agente: o fragmento de DRY ligado ao detector (decisão 7), em `orchestrator\dry_brief.py`; recebe os limites que o check usa.
6. **Feito (03/11):** `docs\duplicacao.md` e ADR 0038. Texto do passo: documento de uso do gate (o que mede, como ajustar, como instalar o `jscpd`) e o ADR da decisão 1, com a emenda à tabela da Especificação.
7. **Gate de mutação** nos arquivos novos (`scripts\mutate.py`).
8. **Ponta a ponta** com o `jscpd` real, no fecho (regra do dono: testes reais só no E2E final): uma tarefa que introduz duplicação e uma que não introduz.

## Limites já conhecidos

- O `jscpd` mede texto/tokens repetidos, não duplicação de intenção; abstrações diferentes com mesma função passam.
- A v5 do `jscpd` é binário autossuficiente: o requisito de Node que este plano temia não se aplica (confirmado no passo 0).
