# Plano: gate de duplicação (DRY)

Estado: plano, nada implementado. Origem: o dono apontou em 02/11/2026 que a duplicação (DRY) é vital e que o `jscpd`, previsto na Especificação, não foi implementado. Conferido em 02/11/2026: não há check de duplicação em `src\forja\checks` nem menção a `jscpd` no código; a Fila e o Registro não o dispensaram.

## O que a Especificação diz

- Linha 16 (políticas como código): cada predicado da biblioteca de engenharia, DRY entre eles, é um objeto com racional, fragmento de prompt, detector, limiar e métrica oposta; o texto que orienta o LLM e a regra que o julga vêm da mesma fonte.
- Linha 400 (camadas transversais às seis linguagens): **jscpd** (duplicação), ao lado de lizard, tree-sitter, Semgrep, OSV-Scanner e gitleaks.
- A tabela de gates não tem linha para duplicação. O gate 8 (métricas estruturais: CRAP ou complexidade acima do limiar, métrica oposta que piorou) é o vizinho natural; ver decisão 1.
- Regras gerais que valem aqui (as mesmas do `plano-gate-10.md`): catraca (só o novo reprova), configuração do repositório prevalece sobre o perfil padrão, check novo nasce em modo observação, ferramenta que falha é `Inconclusive`, nunca aprovação.

## O que a ferramenta faz

**Leitura completa ainda não feita (passo 0 pendente).** Achados preliminares, vindos da leitura da fila 14 em 02/11/2026 e a conferir na versão fixada: a v5 (5.4.2) é binário nativo, sem Node; relatório JSON com `duplicates[]` (cada um com `firstFile` e `secondFile`, `lines`, `tokens`) e `statistics`; configuração em `.jscpd.json`; a página de códigos de saída é ambígua sobre se achar clones falha a execução; `jscpd .` respeita o `.gitignore`. O `jscpd` é referência do dono (Especificação, linha 400) e é seguido como está. Nada abaixo sobre flags, formato de saída, linguagens suportadas ou códigos de saída vale antes do passo 0.

## Decisões

1. **Um check `duplication`, `gate = 8`**, com o seu modo (ADR 0003). Nasce em **observação**. A Especificação não numera um gate para duplicação; o ADR do passo 6 registra a escolha do gate 8 e emenda a tabela.
2. **`jscpd` é transversal**, como lizard, gitleaks e Semgrep: não vira operação de adaptador. O comando entra no `PipelineMeasurer` como parâmetro (`jscpd=`), é achado pela sessão e listado no `doctor`.
3. **Catraca.** Só reprova a duplicação nova ou que piorou. Roda no estado novo e no texto do commit pai, na cópia privada que `ComplexityCheck._before` já faz (`checks\complexity.py`), e compara os clones. Só conta clone que toca arquivo de produção alterado pela tentativa; duplicação antiga é dívida para o planejador, não motivo para recusar uma melhoria alheia. A chave de identidade do clone (para saber o que é "o mesmo clone" antes e depois) sai do formato real de saída, definida depois do passo 0.
4. **Limiares são os padrões do próprio `jscpd`**, ajustáveis por linguagem no `execucao.toml` (mesmo desenho de `thresholds` do `max_ccn`). Sem calibração extra (C2 foi dispensada pelo dono).
5. **Raiz de testes fora da medição por padrão**, ajustável no TOML: repetição em código de teste é frequente e a regra DRY do agente é sobre produção. Usa o `test_root` do adaptador, como o resto da Forja.
6. **`jscpd` ausente, falho ou com saída ilegível: `Inconclusive`**, nunca aprovação. No `doctor`, `jscpd` entra como item obrigatório, como o `gitleaks`, e a linha diz onde ficam as instruções de instalação do próprio `jscpd`. Quem instala é a fila 14 (a Forja passa a instalar as ferramentas externas OSS); até lá, o `doctor` só aponta.
7. **O texto que orienta o agente vem da mesma fonte do detector** (Especificação, linha 16): o fragmento de prompt de DRY e o limiar do check saem do mesmo objeto de política. O passo 5 olha como as instruções atuais tratam DRY (ADR 0036 trata só de dependência) e liga o fragmento ao detector.
8. **Rede:** nada. O `jscpd` lê arquivos locais.

## Passos (um commit cada)

0. **Ler o que falta, por inteiro:** a documentação oficial do `jscpd` (README, opções da linha de comando, relatores, esquema do JSON, linguagens e formatos suportados, arquivo de configuração, ignorados, códigos de saída, requisitos de instalação como Node). Escrever aqui o que a leitura mostrar e corrigir as decisões que divergirem, em especial a 3 (chave do clone) e a 6 (requisito de Node para repositório que não é JavaScript).
1. **Parser** da saída do `jscpd` para um modelo de clones (arquivos, linhas, tamanho). Testes com ferramenta falsa (molde: `FAKE_GITLEAKS`).
2. **Check `duplication`** com a catraca da decisão 3, `gate = 8`, modo observação.
3. **Configuração e sessão:** limiares por linguagem e raiz de testes excluída no `execucao.toml`, descoberta do comando, linha do `doctor`, `Tools`.
4. **Integração:** registro no `PipelineMeasurer.judge` depois de `module_depth`, resumo da preparação e da entrega. Atualizar as listas de checks dos testes (`EVERY_CHECK`, `GATES`, `standard` em `tests\checks\support.py`, ordens em `test_measurer.py` e `test_precision.py`, tabela de `test_pieces.py`).
5. **Instruções ao agente:** o fragmento de DRY ligado ao detector (decisão 7).
6. **Documentação do usuário e ADR:** documento de uso do gate (o que mede, como ajustar, como instalar o `jscpd`) e o ADR da decisão 1, com a emenda à tabela da Especificação.
7. **Gate de mutação** nos arquivos novos (`scripts\mutate.py`).
8. **Ponta a ponta** com o `jscpd` real, no fecho (regra do dono: testes reais só no E2E final): uma tarefa que introduz duplicação e uma que não introduz.

## Limites já conhecidos

- O `jscpd` mede texto/tokens repetidos, não duplicação de intenção; abstrações diferentes com mesma função passam.
- A v5 do `jscpd` é binário autossuficiente (achado preliminar), então o requisito de Node que este plano temia não se aplica; a confirmar no passo 0.
