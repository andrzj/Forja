# 0006. Estado reconstruído só pelos eventos

- Status: Aceito
- Data: 10/10/2026

## Contexto

Uma execução pode durar horas e ser interrompida em qualquer ponto. Se o estado vivesse em memória ou em arquivos paralelos, a retomada dependeria de os dois concordarem.

## Decisão

O log de eventos é a única fonte do estado. Ele é JSONL append-only; cada linha é JSON canônico com `prev` e `hash` encadeados. Um evento é validado contra o estado antes de ser escrito, então o log nunca contém um evento que as regras rejeitam. Há `fsync` em todo evento, menos nos de progresso. Uma última linha truncada é recuperada na abertura e guardada num arquivo `.discarded-N`. Dano em qualquer outra linha recusa a retomada. Os eventos não guardam conteúdo: o payload tem até 4 KiB e as linhas de saída são cortadas em 1 KiB; o conteúdo vive nos artefatos, nas evidências e no log bruto, referenciados por id e hash. Cada evento carrega a versão do esquema, e a leitura converte versões antigas ou recusa as desconhecidas.

## Consequências

- Um estado errado só pode vir de uma sequência de eventos aceita pelas regras; o teste de retomada ponta a ponta interrompe a execução após cada linha do log.
- Escrita lenta por `fsync` em toda transição, aceita em troca de durabilidade.
- Um defeito de gravação torna o log inutilizável até ser reaberto, para nunca anexar sobre uma linha parcial.

Ver a especificação, seção "Resiliência e retomada".
