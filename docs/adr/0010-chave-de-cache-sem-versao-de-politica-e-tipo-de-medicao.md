# 0010. Chave de cache sem versão de política nem tipo de medição

- Status: Aceito
- Data: 10/10/2026

## Contexto

Uma medição só pode ser reaproveitada se foi feita no mesmo contexto. Incluir demais na chave faria o cache falhar sem necessidade; incluir de menos faria um gate decidir com dado de outro contexto.

## Decisão

A chave é o SHA-256 de: commit, ferramenta e versão, `config_hash`, toolchain e versão, plataforma e o escopo medido, em ordem canônica. A versão das políticas e o tipo de medição ficam de fora: a política julga a evidência, não a produz, e a evidência registra a versão que a julgou. O cache existe em memória e só vale dentro de uma execução. Na retomada, o índice de evidências em disco responde se uma execução de ferramenta já aconteceu.

## Consequências

- Mudar um limiar não obriga a medir de novo.
- A reutilização entre execuções continua fora de escopo.
- Uma ferramenta nova de versão diferente gera chave diferente, sem lógica especial.

Ver a especificação, seção "Contrato 5: gate", parágrafo "Chave de cache".
