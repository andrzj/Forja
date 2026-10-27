# 0029. O teste diferencial só executa com casos declarados no repositório

## Contexto

A Especificação manda o gate 11 reprovar, em refatoração, saída nova diferente da antiga para as mesmas entradas, ou regressão de tempo ou memória acima do limite, usando as entradas sintéticas dos geradores e fakes dos E2E. Não diz onde os casos ficam. O plano inicial os tirava do manifesto de testes do autor de testes, mas `forja refatorar` não tem autor de testes, e o esquema do manifesto (testes e geradores com semente) não tem comando, entrada nem regra de comparação.

## Decisão

- **Os casos são declarados na configuração do repositório**, em `[[differential.cases]]`, como o comando de E2E do gate 6. Cada caso tem nome, comando (lista de argumentos; programa de shell recusado), diretório de execução e arquivo de entrada opcionais, e a lista do que se compara: `stdout`, `exit_code` ou `file`, cada um com a regra `bytes`, `json` ou `ignore` (expressões regulares das linhas descartadas antes de comparar os bytes).
- **Sem regra declarada, a diferença é diferença.** Sem `outputs`, o caso compara a saída padrão e o código de saída, byte a byte. A Forja não inventa regra de comparação.
- **Sem casos, o gate não executa** e a preparação e a entrega dizem “Teste diferencial não executado: sem casos”, como o E2E sem comando e o SAST sem regras (ADR 0024).
- **Os casos não mudam durante a execução.** Vêm da política congelada na confirmação (`policy.json`), não da worktree da tentativa. Os arquivos de entrada são copiados da base para fora da worktree, uma vez, e toda execução lê a cópia; o implementador não pode editá-los para silenciar uma diferença.
- **A seção só entra no digest da política quando existe**, como as camadas do ADR 0028.

## Alternativas

- *Casos no manifesto de testes.* Exigiria autor de testes em `refatorar` e um esquema novo no manifesto; muda o planejador por causa de um gate.
- *Casos gerados pelo agente.* O agente que refatora escolheria o que prova que não mudou nada.
- *Comparação semântica automática (ordem, tipos, datas).* Seria regra inventada; o dono do repositório declara a que vale.

## Consequências

O gate depende de o dono escrever os casos. Em compensação, o que vale como “mesma saída” é dele e fica no repositório. Entrada que o caso lê de um arquivo precisa existir na base. I/O não é medido. O plano está em `docs/plano-gate-11.md`.
