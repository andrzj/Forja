# 0002. Uma sessão da Forja por repositório

- Status: Aceito
- Data: 10/10/2026

## Contexto

O log de eventos é a única memória de uma execução. Durante a discussão do lock surgiu a objeção de que recusar a segunda sessão sem espera poderia deixar uma tarefa por fazer e comprometer a cadeia de eventos. A objeção se resolveu ao fixar que só pode existir uma sessão por repositório: o log tem sempre um único escritor, e a segunda sessão não perde trabalho porque nunca começa a escrever.

## Decisão

O lock é um diretório em `locks/<id>` com `owner.json` (PID, máquina, token de criação do processo e um valor único). Dono morto é detectado e o lock é assumido por um diretório de guarda e um `rename`. A segunda sessão segue uma política escolhida pelo chamador: `LockPolicy.refuse()` ou `LockPolicy.wait_for(limite)`. O mutex de git é separado, vale só para comandos que escrevem e nunca fica preso durante a chamada ao agente.

## Consequências

- O padrão entre recusar e esperar ainda não foi escolhido; fecha no incremento 1 (questão 10 do plano). Recomendação: recusar no modo interativo, esperar em CI.
- O lock fica no diretório de dados do usuário, então não protege contra outra máquina no mesmo repositório compartilhado.
- Falha por tempo esgotado do lock ou do mutex é falha transitória.

Ver a especificação, seção "Exclusividade e retomada".
