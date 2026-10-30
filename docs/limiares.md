# Limiares sem calibração

Lista dos limiares da Forja que ainda não foram calibrados com dados de revisão (`forja revisao` sobre execuções reais, do dono). Nenhum valor foi mudado ao escrever este documento. Fila 6, parte C, passo C1 (`docs\plano-medicoes-e-calibracao.md`).

Todos os gates abaixo estão em **observação** (medem e reportam, não bloqueiam), exceto `complexity`, que é bloqueante com um valor que não é nosso (o padrão do `lizard`). Registro dos modos: `src\forja\checks\specs.py`. O dono ajusta cada valor por linguagem na configuração (`[checks.<check>.thresholds.<linguagem>]`); o que está aqui é o padrão do código.

## Limiares numéricos

| Gate | Check | Limiar | Valor atual | Fonte do número | Onde está |
| --- | --- | --- | --- | --- | --- |
| 7 | `mutation` | `min_score` | 0,80 (0,70 para Python e Go) | Especificação, linha 404: “valores iniciais: 0,80; 0,70 para Python e Go, onde a mutação é mais frágil”. Sem dado. | `checks\mutation.py` (`DEFAULT_MIN_SCORE`, `LOWER_MIN_SCORE`, `LOWER_LANGUAGES`) |
| 8 | `complexity` | `max_ccn` | 15 | Padrão do próprio `lizard` (comentário no código). Bloqueante. | `checks\complexity.py` (`DEFAULT_MAX_CCN`) |
| 8 | `crap` | `max_crap` | 30,0 | “O limiar clássico” (comentário no código). O comentário diz “calibrated in step 9”, mas nenhuma calibração foi feita. | `checks\crap.py` (`DEFAULT_MAX_CRAP`) |
| 8 | `module_depth` | `max_interface_ratio` | 1,0 | Palpite (comentário: “a guess until the calibration”). | `checks\module_depth.py` (`DEFAULT_MAX_RATIO`) |
| 8 | `module_depth` | `min_statements` | 10 | Sem fonte registrada no código. | `checks\module_depth.py` (`DEFAULT_MIN_STATEMENTS`) |
| 9 | `package_metrics` | `max_distance` | 0,8 | Palpite (comentário: “a guess until the calibration”). | `checks\package_metrics.py` (`DEFAULT_MAX_DISTANCE`) |
| 9 | `package_metrics` | `min_types` | 3 | Sem fonte registrada no código. | `checks\package_metrics.py` (`DEFAULT_MIN_TYPES`) |
| 10 | `new_dependency` | `min_age_days` | 30 | Sem fonte registrada no código; documentado em `docs\seguranca-e-dependencias.md`. | `checks\new_dependency.py` (`DEFAULT_MIN_AGE_DAYS`) |
| 10 | `new_dependency` | `min_downloads` | 100 | Idem. | `checks\new_dependency.py` (`DEFAULT_MIN_DOWNLOADS`) |
| 11 | `differential` | `max_time_ratio` | 1,25 | Palpite (comentário: “a guess until the calibration of queue item 6”). | `checks\differential.py` (`DEFAULT_MAX_TIME_RATIO`) |
| 11 | `differential` | `max_memory_ratio` | 1,25 | Mesmo palpite do tempo. | `checks\differential.py` (`DEFAULT_MAX_MEMORY_RATIO`) |
| 11 | `differential` | `runs` | 3 | Sem fonte registrada; número de execuções por caso a cada tentativa (a mediana). | `checks\differential.py` (`DEFAULT_RUNS`) |
| 12 | `voice` | `max_dashes` | 3 | Comentário: travessões que um arquivo acrescenta “before it reads as excess”. Sem dado. | `checks\voice_markers.py` (`MAX_DASHES`) |
| 12 | `comments` | `MIN_WORDS` | 2 | Comentário no código: um comentário de uma palavra é rótulo. Constante, não ajustável na política. | `checks\comments.py` |
| 12 | `comments` | `REPEAT_RATIO` | 0,75 | Fração das palavras do comentário que o código já tem. Sem fonte; constante, não ajustável na política. | `checks\comments.py` |
| 1 | `scope` | `max_files`, `max_lines` | 8 arquivos, 400 linhas por tarefa | Orçamento da execução (`files_per_task`, `lines_per_task`); a Especificação põe os valores padrão em aberto (Plano, questão 6). | `orchestrator\config.py` (linhas 87 e 88) |

## Gates sem número

`pass_through` (gate 8) não tem limiar numérico: reprova função nova que só repassa os próprios argumentos. A calibração dele, se houver, é de regra (o que conta como repasse), não de valor. O mesmo vale para `dependency_cycles`, `layer_rules`, `citations`, `traceability`, `change_record`, `readme`, `doc_drift` e `adr`: dependem de regra, não de limiar.

## O que falta para calibrar (C2)

Relatórios de `forja revisao` de execuções reais revisadas pelo dono: eles dão, por gate e por linguagem, o que passou e o que reprovou entre as tentativas que chegaram ou não à principal. Sem eles nada aqui muda, e a promoção de gates de observação para bloqueante (fila 7) fica parada.
