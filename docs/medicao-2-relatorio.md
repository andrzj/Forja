# Medição 2: Forja contra a linha de base (relatório)

Protocolo: [medicao-2.md](medicao-2.md). Resultados brutos: `%LOCALAPPDATA%\forja-medicao\results.jsonl` (30 execuções contadas; o piloto, repetição 0, fica fora). Objetivo medido: refatorar. Braço A: um único prompt no Claude Code. Braço B: Forja. Mesmo modelo, mesmas ferramentas, teto de 200 mil tokens por execução.

## Resultado

| Tarefas médias (6 por braço) | Aceitas | Regressões | Tokens | Tempo |
|---|---|---|---|---|
| A (só prompt) | 4 de 6 (67%) | 0 | 115.952 | 359 s |
| B (Forja) | 6 de 6 (100%) | 0 | 158.552 | 478 s |

| Repositório | Braço | Aceitas | Tokens (soma de 3) | Tentativas (soma) | Tempo |
|---|---|---|---|---|---|
| `inventory` | A | 2 de 3 | 61.157 | 3 | 188 s |
| `inventory` | B | 3 de 3 | 74.833 | 9 | 229 s |
| `scanner` | A | 2 de 3 | 54.795 | 3 | 171 s |
| `scanner` | B | 3 de 3 | 83.719 | 10 | 249 s |
| `plain` (controle) | A / B | 3 de 3 / 3 de 3 | 14.038 / 12.967 | 3 / 3 | 78 s / 91 s |
| `shop` (controle) | A / B | 3 de 3 / 3 de 3 | 22.226 / 16.911 | 3 / 3 | 88 s / 83 s |
| `web` (controle) | A / B | 3 de 3 / 3 de 3 | 14.408 / 23.656 | 3 / 3 | 68 s / 86 s |

Nenhuma execução estourou o teto de tokens. Nenhuma teve regressão no oráculo (10.830 casos em `inventory`, 7.522 em `scanner`). Nenhuma deixou função acima de CCN 15.

Todas as 15 execuções do braço B têm tokens e tentativas maiores que zero; são medição válida.

## Aplicação da regra (sem ajuste depois dos números)

1. Inconclusivo: não se aplica. O braço A ficou em 67% nas tarefas médias (abaixo de 90%).
2. Seguir: se aplica. Aceitação da Forja 33 pontos percentuais acima (mínimo 15); regressões 0, iguais às da linha de base; tokens 1,37× (máximo 2×).

Recomendação de quem mediu: **Seguir, com as ressalvas abaixo.** A decisão final é do dono.

## Ressalvas

- **As duas reprovações do braço A foram só por `format`** (`inventory` e `scanner`, repetição 2 de cada): refatoração correta, sem regressão, sem função complexa, código sem formatar. É um resultado, não um erro do juiz.
- **O braço B normaliza o estilo** (commit `style:`) e o A não. Parte da vantagem pode vir daí, e não dos portões ou das tentativas guiadas. Esta medição não separa as duas causas. Uma variante do A com `ruff format` ao final separaria.
- **A vantagem é de 2 execuções em 6 por braço.** Pouca força estatística; não se afirma significância.
- **Custo de tentativas:** o B precisou de 3 a 4 tentativas em todas as 6 execuções médias; o A acertou na primeira em todas. Nos controles, 1 tentativa nos dois braços.
- **Tempo:** B levou 1,33× o tempo de A nas tarefas médias.
- Valem as limitações do protocolo: mesmo autor da Forja e das tarefas, só Python, só refatoração, só Claude Code, uma versão do modelo, critério objetivo e não revisão humana.
- Houve execuções descartadas durante a coleta (limite de uso da conta, execuções incompletas anteriores bloqueando o B). Foram refeitas e ficam em `results-invalid.jsonl`; não entram nos números.

## O que fazer em seguida

Seguir para o incremento 3. Registrar a questão do estilo como pergunta aberta: se o ganho de aceitação sobrevive quando o A também formata.
