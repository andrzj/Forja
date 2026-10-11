# 0011. A retomada fecha as operações abertas com um efeito

- Status: Proposto
- Data: 10/10/2026

## Contexto

Uma intenção sem efeito indica que a execução parou no meio da operação. A tabela de idempotência diz como verificar cada operação e se é seguro repetir, mas não diz como o log registra o desfecho. Como um `operation_id` não pode ser usado duas vezes, repetir a operação exige um id novo, e a intenção antiga não pode ficar aberta para sempre.

## Decisão

`resume(log, reconcile)` mata o processo remanescente, pede o veredito ao reconciliador e fecha cada operação aberta com um `effect` cujo payload tem `reconciled` (`already_done`, `redo` ou `discard_attempt`) e `infra_failure`. Em `redo`, quem repete usa um novo `operation_id`. Em `discard_attempt`, a tentativa passa para `discarded` antes do efeito, e repetir a retomada depois de uma interrupção é seguro. O intent guarda os insumos da reconciliação no payload.

## Consequências

- O `effect` passa a significar "operação encerrada", não só "operação concluída"; quem lê o log olha `reconciled`.
- Esta decisão preencheu uma lacuna da especificação e ainda não foi revista de forma específica; por isso o status é Proposto.
- O teste de retomada (`tests/e2e`) depende deste formato.

Ver a especificação, seção "Intenção, efeito, efetivação".
