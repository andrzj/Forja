# Plano: melhorias da interface de terminal

Estado (08/11/2026): passos 0 a 6 feitos; falta só o E2E real, que é do dono. Origem: ordem expressa do dono (08/11/2026), fora da fila, para as melhorias da UI registradas em `NOTAS.md`. Referência: Especificação, "Interface de terminal e acompanhamento" (conteúdo da tela: cabeçalho com objetivo, branch e tempo; atalhos `d` detalhes, `l` log completo, `q` interromper com segurança) e a tabela "Gates, em ordem" (gates 1 a 14).

## Como está hoje (lido em `src\forja\ui` e `src\forja\cli\keys.py`)

- `full.py::ForjaApp`: `ctrl+k` e `ctrl+c` param (a primeira vez salva e deixa retomar, a segunda sai na hora); `q` e `escape` só fecham a ajuda ou saem depois do fim; `t` troca o tema; `?` abre a ajuda. Não há `d` nem `l`.
- `cli\keys.py::KEYS` (linha viva e texto simples) só conhece `ctrl+k`, `ctrl+c` e `t`; `cli\run.py` para com `ctrl+k` ou `ctrl+c`. `live.py::HINT` diz "ctrl+k interrompe".
- A barra (`panels.py::gates_line`, `live.py::_gates`) mostra os 28 checks de `view.py::GATES`, um a um.
- O cabeçalho (`panels.py::header`/`_cost`) mostra os tokens da execução inteira; não há gasto por tarefa.
- A atividade (`view.py::ViewModel.feed`) guarda só as 60 últimas linhas; as rejeições, as 20 últimas, cortadas com reticências na tela.

## Decisões do dono (08/11/2026)

1. `d` mostra a tarefa atual inteira: id, intenção, tentativa, cada check com nome completo, gate e estado, e o texto inteiro de cada rejeição da tarefa, sem corte.
2. `l` mostra a atividade inteira desde o início, rolável.
3. A barra mostra os gates 1 a 12 (os da tentativa); 13 e 14 são do documentador e ficam fora.
4. O cabeçalho mostra os tokens da tarefa atual ao lado do total da execução.

## Decisões minhas, dentro da Especificação

- `q` passa a interromper com segurança durante a execução, como `ctrl+k`: a primeira salva e deixa retomar, a segunda sai na hora. Depois do fim, `q` sai, como hoje. Com a ajuda, os detalhes ou o log abertos, `q` e `escape` fecham a tela aberta. `ctrl+k` e `ctrl+c` continuam valendo (o `ctrl+c` o terminal manda de qualquer jeito).
- Estado de um gate na barra, a partir dos seus checks: reprovado se algum reprovou; em andamento se algum roda; aprovado se todos passaram; pendente nos demais casos. A ordem do pipeline não é a dos números (`complexity`, do gate 8, roda antes de `mutation`, do 7), então um gate com parte aprovada e parte por medir fica pendente, não em andamento.
- O mapa check para gate fica em `view.py` (a UI não importa `checks`), com teste que o confere com `checks\specs.py::default_registry`.
- Os tokens da tarefa vêm dos eventos `usage` já gravados (`target_id` é a tentativa, `T1-a2`; a tarefa é o prefixo), então a retomada os refaz pelo `replay`.
- `d` e `l` só existem na tela cheia. Na linha viva e no texto simples a notícia já sai inteira no terminal; lá só entra o `q`.
- O log completo guarda toda linha de atividade da tarefa em tela, sem limite, mais uma linha por check que começa a medir.

## Passos (um commit cada)

0. Este plano e o registro no Plano de execução.
1. Tecla `q`: `full.py`, `cli\keys.py`, `cli\run.py`, `live.py::HINT`, rodapé, faixa e ajuda de `panels.py`. Testes em `tests\ui\test_full.py`, `tests\cli\test_run.py` e nos de `panels`/`live`.
2. Barra pelos gates 1 a 12: mapa `GATE_OF` e agregação em `view.py`; `panels.py::gates_line` e `live.py::_gates` com nomes curtos dos gates. Testes, inclusive o mapa contra o registro.
3. Tokens da tarefa no cabeçalho: `ViewModel` soma por tarefa, `View.task_tokens`, `panels.py::_cost` com a parte "tarefa" (cai antes do tempo quando falta largura, nunca antes dos tokens da execução).
4. Tecla `d`: painel de detalhes em `full.py`, conteúdo puro em `panels.py::details`, rolável.
5. Tecla `l`: `ViewModel.log` sem limite, `View.log`, painel em `full.py`, conteúdo em `panels.py::log_lines`, rolável.
6. Fecho: gate de mutação (`scripts\mutate.py`) nos arquivos mudados, `ruff`, `mypy`, `tests\ui` e `tests\cli`.

E2E real (ver as telas numa execução real) é do dono.
