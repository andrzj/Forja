# 0020. A mutação de Python usa motor próprio

## Contexto

A especificação previa o mutmut para a mutação de Python. O mutmut 3.8.0 recusa rodar no Windows
nativo ("To run mutmut on Windows, please use the WSL"; issue `boxed/mutmut#397`), e a Forja não
exige WSL (ADR 0018). O mutmut 2.5.1 roda no Windows nativo, mas só com `PYTHONUTF8=1`, é a linha
antiga da ferramenta e não foi verificado em Python 3.12. O motor próprio (commit `5d80fbc`) já
existe e reproduz os pontos de mutação e a redação do `unclebob/mutator`.

## Decisão

- A mutação de Python usa o motor próprio em `src/forja/mutation`. O gate 7 de Python não depende do
  mutmut.
- Isso é exceção à tabela de ferramentas da especificação. As demais linguagens seguem a tabela
  (PIT, gremlins, Stryker.NET, StrykerJS).
- Vale a regra de que ferramenta escrita internamente só vira gate depois de validada contra uma
  ferramenta de referência num repositório conhecido. O gate 7 de Python nasce em `OBSERVATION`
  até essa validação.

## Consequências

A Forja mantém o código do motor e responde por sua correção. A validação contra referência passa a
ser requisito do passo 9 do 3b.
