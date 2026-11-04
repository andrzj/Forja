# Duplicação (DRY): o gate de código repetido

A Forja reprova a tentativa que acrescenta código repetido a um arquivo de produção. Quem mede é o `jscpd` (ADR 0038). O check é o `duplication`, do gate 8, e nasce em modo observação: reporta e não reprova até o repositório promovê-lo.

## O que mede

- **Só duplicação nova.** O `jscpd` roda com `--baseline-from-ref <commit pai>` e marca cada clone como novo quando o conteúdo do fragmento não existe naquele commit. A identidade do clone é o hash do conteúdo: mover o arquivo, deslocar linhas ou trocar o fim de linha não a muda. Uma cópia a mais do que o commit pai tinha também é nova.
- **Só em arquivo de produção que a tentativa mudou.** Clone novo com um lado em arquivo de produção alterado vira achado, um por lado, com caminho, linha, tamanho do clone e o outro lado. Duplicação antiga, ou nova só entre arquivos que a tentativa não tocou, não reprova: é dívida para o planejador.
- **Sem arquivo de produção alterado, não roda.**
- **Testes ficam de fora.** Os arquivos de teste (rastreados e mudados) vão em `ignore`: repetir preparação de teste é comum, e a regra DRY do agente é sobre produção.
- **Só clones exatos**, no modo `mild` do `jscpd`. Renomeados, parecidos e semânticos não são ligados.
- **Mede texto repetido, não intenção.** Duas abstrações diferentes com a mesma função passam.

## Ajustar

Os limites são globais, os padrões do próprio `jscpd`. Não existe limiar por linguagem.

```toml
[checks.duplication.limits]
min_tokens = 50
min_lines = 5
```

`min_tokens` e `min_lines` são o tamanho a partir do qual uma passagem repetida é clone. O mesmo valor entra no texto que a Forja dá ao agente que escreve código (seção `## Duplication` do pacote, `orchestrator\dry_brief.py`), então o aviso e o julgamento concordam. Receber a instrução: implementador e correção. Autor de testes, documentador, especificador e arqueólogo não a recebem.

Para promover o gate a bloqueante, use `mode = "blocking"` em `[checks.duplication]`, como nos outros checks.

## Quando fica sem resposta

Falha da ferramenta nunca aprova: o resultado é `Inconclusive`. Isso vale para o `jscpd` que não inicia, para saída diferente de 0 e para relatório ausente, velho ou ilegível. A Forja não liga nenhuma porta do `jscpd` (`--threshold`, `--exit-code`, `--fail-on-new-clones`), então saída diferente de 0 é sempre falha.

## Instalar o `jscpd`

O `jscpd` é obrigatório no `forja doctor`. A versão 5 é um binário autossuficiente: não precisa de Node. `forja instalar` o instala na pasta da Forja (ver `docs\instalacao.md`). O `git` precisa estar presente, porque o `--baseline-from-ref` o usa.

## Limites

- **A tentativa pode esconder clone.** O `jscpd` respeita `.gitignore`, `.ignore` e as regiões `jscpd:ignore-start` e `jscpd:ignore-end`. Um agente que escreve um desses ou marca uma região esconde o clone da medida. Desligar o `.gitignore` varreria `.venv` e dependências, então a Forja não o faz. A revisão do ramo é o que pega isso.
- **Configuração da tentativa não vale.** A Forja passa `--config` explícito, que vence `.jscpd.json` e a chave `jscpd` do `package.json`.
- **Em aberto para o E2E:** o comportamento do `--baseline-from-ref` numa worktree ligada do git; se o `jscpd` real acha clone do trabalho ainda não commitado; globs com barra invertida no Windows. Se o `--baseline-from-ref` falhar na worktree, o plano prevê cair para `--baseline` em arquivo temporário.
- A barra de gates da UI ainda não mostra o `duplication`.

O plano está em `docs\plano-gate-duplicacao.md`.
