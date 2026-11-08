# Plano — E2E reais executados pelo LLM (fila 18)

Estado (08/11/2026): plano escrito; passos 1 a 3 (E2E 1 a 3) feitos, próximo o passo 4. Origem: ordem expressa do dono (08/11/2026): o E2E real deixa de ser do dono; o LLM o executa. Isso muda a regra 6 do Plano de execução e o "é do dono" das filas 13 a 17 e dos itens concluídos que dizem "falta só o E2E real".

## Escopo

Os E2E reais que `NOTAS.md` lista como por fazer:

| # | E2E | Origem | Ambiente |
| --- | --- | --- | --- |
| 1 | Rejeição dos gates 6, 9 e 11 | filas 1, 4, 5 | Windows, CLI `claude` real |
| 2 | SAST e OSV (gate 10) | fila 1 | Windows, ferramentas reais |
| 3 | Voz (efeito da instrução) | fila 10 | Windows, `claude` real |
| 4 | Diário de bordo no ramo | fila 5A | Windows, `claude` real |
| 5 | Instalação editável | fila 12 | Windows |
| 6 | `jscpd` real: tarefa que duplica e tarefa que não duplica | fila 13, passo 8 | Windows, `claude` real |
| 7 | Instalação em diretório limpo (`forja instalar` e uma execução) | fila 14, passo 10 | Windows |
| 8 | `mypy` real: tarefa com erro de tipo e tarefa sem | fila 15, passo 6 | Windows, `claude` real |
| 9 | Propriedades com as ferramentas reais | fila 16, passo 7 | Windows, `claude` real |
| 10 | Telas da UI (`d`, `l`, `q`, barra, tokens) numa execução | fila 17 | Windows, `claude` real, tela cheia |

## Regras do plano

1. Um E2E por vez, na ordem da tabela, cada um com seu commit e sua linha no Registro: o que rodou, o comando, o resultado, o custo em tokens e o que falhou.
2. Cada E2E roda num repositório descartável criado fora de `forja\` (pasta temporária), nunca no repositório da Forja.
3. "Máquina limpa" (E2E 7) = diretório novo, ambiente virtual novo e cache de ferramentas vazio da Forja, no Windows. Linux está fora do plano, por ordem do dono (08/11/2026). Não há máquina virgem aqui; o que isso não prova (programas já presentes no PATH do dono) é dito no Registro como limite.
4. Falha do E2E é achado: o LLM corrige a causa na Forja (um commit por correção, com teste que a pegaria) e repete o E2E. Não é pendência do dono.
5. O que o E2E não consegue verificar sem o dono (aparência subjetiva da tela, qualidade do texto da voz) o LLM entrega como captura ou saída e marca no Registro como "para o dono olhar", sem bloquear o fechamento.
6. Custo: cada execução com `claude` real gasta tokens do plano do dono. Antes de cada E2E o LLM diz em uma linha qual será e roda; não pergunta.

## Passos

0. Este plano e a mudança das regras e da fila (feito).
1 a 10. Um passo por E2E da tabela, na ordem.
11. Fechar: `NOTAS.md`, a Fila e os "falta só o E2E real" dos itens concluídos atualizados com o resultado.
