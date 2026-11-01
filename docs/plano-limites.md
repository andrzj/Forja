# Plano: limites conhecidos (fila 12)

Origem: ordem expressa do dono (01/11/2026). Corrige os limites listados em `NOTAS.md`, exceto a guarda de git com `paralelismo` acima de 1 (o dono mandou deixar como está). Um passo por commit, cada um com testes, gate de mutação no código novo e entrada no Registro de `docs\Plano de execução.md`.

| Passo | Limite | Correção |
| --- | --- | --- |
| 1 | O ambiente virtual da execução não vê instalação editável do próprio repositório (layout `src` com `pip install -e`) | O `forja-base.pth` processa também os `.pth` do `site-packages` base, ou o ambiente recebe o caminho do repositório. Prova com repositório de layout `src`. |
| 2 | A barra de gates da UI não mostra os gates 9 a 11 | Os gates 9 a 11 entram na barra e nos testes da UI. |
| 3 | O diário no ramo vai sem redação | O diário copiado ao ramo passa pela mesma redação do `.forja-agent\diary.md`. |
| 4 | O gate 11 mede memória só no Windows | Medição em Linux e macOS, com testes por plataforma. |
| 5 | Sem teste de queda entre o `BLOCKED` e o efeito (fila 9) | Teste que interrompe nesse ponto e confere a retomada sem estado partido. |
| 6 | O comentário de `checks\crap.py` diz "calibrated in step 9" sem calibração | Texto corrigido: a calibração foi dispensada. |
| 7 | `REASON_LIMIT` (1500) em `task_cycle.py` corta o motivo ao gravar no log | O limite sai: o motivo é gravado inteiro (decisão do dono, 01/11). |

Antes: gate de mutação nas linhas do diário e nos sobreviventes antigos de `agent_runner.py`, `measurer.py` e `session.py` (pedido do dono, mesma data).
