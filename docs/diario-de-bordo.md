# Diário de bordo

Cada chamada a um agente é nova. Sem ajuda, o agente de uma tentativa só saberia da última rejeição, e ninguém veria o padrão de duas tentativas que partem da mesma hipótese e falham no mesmo gate. O diário de bordo é o histórico das tentativas, mostrado ao agente, ao revisor e ao ramo. Não há configuração: vale em toda execução.

## O que é

Uma projeção do log de eventos da execução (`orchestrator\diary.py`). A Forja não guarda nada a mais: o diário é lido do que o log já tem, então uma execução retomada, ou um log cortado na última linha, dá o mesmo texto. Cada entrada é uma tentativa:

- **o que o agente disse**: o texto que ele deu ao terminar (o `reason` da ação), como foi guardado;
- **o desfecho**: rejeitada (com o gate e os achados), aprovada (com os gates que passou), descartada (com o motivo; a falha de infraestrutura é marcada) ou não terminou;
- **o que a Forja decidiu**: etapa esgotada e tarefa bloqueada, com o motivo.

## Regra de fidelidade

Tudo o que o diário mostra ao modelo é fiel ao que foi escrito. A fala do agente e o motivo da rejeição não são resumidos, cortados nem omitidos, e nenhuma tentativa é deixada de fora (decisão do dono, 01/11/2026: todo input e output entre processos, agentes e etapas é fiel, verdadeiro e fidedigno). Texto de várias linhas vai citado, com `> ` em cada linha, para não passar por título ou seção do pacote.

## Onde aparece

| Onde | O quê | Limites |
| --- | --- | --- |
| Arquivo `.forja-agent\diary.md` do pacote do agente, e seção “Earlier attempts of this stage” | O arquivo traz **todas** as tentativas anteriores da mesma etapa, a partir da segunda, cada uma inteira (o que o agente disse e o motivo). Passa pelo redator, como README e fatos. A seção do pacote traz a **ordem imperativa de ler o arquivo antes de agir**; só existe quando há tentativa anterior. | Nenhum corte e nenhuma omissão. O agente não pode editar o arquivo (negado nas permissões do Claude Code e do Grok) e a Forja confere, ao receber o trabalho, que ele é idêntico ao gravado; se mudou ou sumiu, o trabalho é rejeitado. |
| Pacote do agente, seção “The previous attempt was rejected” | O motivo da última rejeição e, logo abaixo, o que o agente disse naquela tentativa, citado. | O motivo é guardado no log inteiro, sem limite (o `REASON_LIMIT` saiu na fila 12, 01/11/2026); o diário não corta nada. |
| Pacote do agente, seção “Attack the hypothesis” | Pedido para escrever a hipótese em uma frase no `reason`, quando duas ou mais tentativas da etapa foram rejeitadas no mesmo `gate N (check)`. | Texto fixo da Forja, baseado em “Attack the Premise” da skill `ub-mode` (`unclebob/ub-mode`), com “hypothesis” no lugar de “premise”. Descarte por infraestrutura não conta. |
| Resumo da execução, seção “Diário de bordo” | Por tarefa, cada tentativa com o que disse e o motivo, e as decisões da Forja. | Sem corte; só o espaço em branco entre as palavras vira um espaço, para caber em uma linha. O resumo não vai ao modelo e não é commitado. |
| Ramo da tarefa, `docs/mudancas/<tarefa>-diario.md` | Todas as tentativas de todas as etapas da tarefa, rejeitadas inclusive, e as decisões, em Markdown, citadas e sem corte. | Escrito pela Forja junto com o registro de mudança, no commit `docs:` do documentador. Deixa de fora a tentativa do documentador que está sendo julgada. |

As tentativas rejeitadas continuam sem commit de código; o diário as registra como texto.

## O que o diário não faz

- **Não confere a hipótese.** A Forja pede que ela seja escrita no `reason`, mas não verifica que foi.
- **Não guarda nada entre execuções.** Cada execução tem o seu, como os fatos.
- **Não registra papel nem CLI por entrada.** O log guarda só o sufixo do id da etapa e a CLI vem da configuração.
- **“Devolvida ao autor de testes” e “integração desfeita” não aparecem** como decisão própria: não têm transição no estado.
- **O arquivo do ramo passa pelo redator**, o mesmo do `.forja-agent/diary.md`: segredo é mascarado, o resto do texto fica inteiro. O corpo do commit, que também traz a fala do agente, não passa por ele.
- **O gate de voz só observa o arquivo.** Ele julga as linhas adicionadas de toda documentação, mas está em modo observação.
- **Skills e `CLAUDE.md` do usuário na chamada do Claude Code** (`--setting-sources user`, `--disable-slash-commands`): só uma chamada real diz o que entra. O efeito medido do diário pode se misturar com o das instruções do perfil.
- **A seção do resumo lista todas as tarefas**, inclusive as integradas sem rejeição, com uma linha por tentativa.

A decisão está em [ADR 0031](adr/0031-o-diario-e-uma-projecao-do-log-fiel-ao-que-foi-escrito.md); o plano, em [plano-diario-de-bordo.md](plano-diario-de-bordo.md).
