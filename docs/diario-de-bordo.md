# Diário de bordo

Cada chamada a um agente é nova. Sem ajuda, o agente de uma tentativa só saberia da última rejeição, e ninguém veria o padrão de duas tentativas que partem da mesma hipótese e falham no mesmo gate. O diário de bordo é o histórico das tentativas, mostrado ao agente, ao revisor e ao ramo. Não há configuração: vale em toda execução.

## O que é

Uma projeção do log de eventos da execução (`orchestrator\diary.py`). A Forja não guarda nada a mais: o diário é lido do que o log já tem, então uma execução retomada, ou um log cortado na última linha, dá o mesmo texto. Cada entrada é uma tentativa:

- **o que o agente disse**: o texto que ele deu ao terminar (o `reason` da ação), como foi guardado;
- **o desfecho**: rejeitada (com o gate e os achados), aprovada (com os gates que passou), descartada (com o motivo; a falha de infraestrutura é marcada) ou não terminou;
- **o que a Forja decidiu**: etapa esgotada e tarefa bloqueada, com o motivo.

## Regra de fidelidade

Tudo o que o diário mostra ao modelo é fiel ao que foi escrito. A fala do agente e o motivo da rejeição não são resumidos nem reescritos. Texto de várias linhas vai citado, com `> ` em cada linha, para não passar por título ou seção do pacote. Os únicos cortes são os que a Forja diz no próprio texto (abaixo).

## Onde aparece

| Onde | O quê | Limites |
| --- | --- | --- |
| Pacote do agente, seção “Earlier attempts of this stage” | As tentativas anteriores **da mesma etapa**, a partir da segunda. As 3 últimas rejeitadas ou não terminadas vão completas; as mais antigas e todo descarte, em uma linha. Passa pelo redator, como README e fatos. | Linha única de 160 caracteres, terminada em `...`. Teto de 6000 caracteres: caem primeiro as linhas mais antigas, depois as completas mais antigas, e o texto diz quantas tentativas ficaram de fora. A rejeição mais recente aparece também em “The previous attempt was rejected”, de propósito. |
| Pacote do agente, seção “Attack the hypothesis” | Pedido para escrever a hipótese em uma frase no `reason`, quando duas ou mais tentativas da etapa foram rejeitadas no mesmo `gate N (check)`. | Texto fixo da Forja, baseado em “Attack the Premise” da skill `ub-mode` (`unclebob/ub-mode`), com “hypothesis” no lugar de “premise”. Descarte por infraestrutura não conta. |
| Resumo da execução, seção “Diário de bordo” | Por tarefa, cada tentativa com o que disse e o motivo, e as decisões da Forja. | Corte de 1500 caracteres (o mesmo limite do ciclo; na prática não corta). O resumo não vai ao modelo e não é commitado. |
| Ramo da tarefa, `docs/mudancas/<tarefa>-diario.md` | Todas as tentativas de todas as etapas da tarefa, rejeitadas inclusive, e as decisões, em Markdown, citadas e sem corte. | Escrito pela Forja junto com o registro de mudança, no commit `docs:` do documentador. Deixa de fora a tentativa do documentador que está sendo julgada. |

As tentativas rejeitadas continuam sem commit de código; o diário as registra como texto.

## O que o diário não faz

- **Não confere a hipótese.** A Forja pede que ela seja escrita no `reason`, mas não verifica que foi.
- **Não guarda nada entre execuções.** Cada execução tem o seu, como os fatos.
- **Não registra papel nem CLI por entrada.** O log guarda só o sufixo do id da etapa e a CLI vem da configuração.
- **“Devolvida ao autor de testes” e “integração desfeita” não aparecem** como decisão própria: não têm transição no estado.
- **O arquivo do ramo não passa pelo redator.** Ele traz a fala do agente e o motivo como estão no log, como o corpo do commit já traz. A redação cobre só o que a Forja envia a terceiros (ADR 0009), e a Forja nunca faz push (ADR 0013). Se o repositório for publicado, revise o arquivo antes.
- **O gate de voz só observa o arquivo.** Ele julga as linhas adicionadas de toda documentação, mas está em modo observação.
- **Skills e `CLAUDE.md` do usuário na chamada do Claude Code** (`--setting-sources user`, `--disable-slash-commands`): só uma chamada real diz o que entra. O efeito medido do diário pode se misturar com o das instruções do perfil.
- **A seção do resumo lista todas as tarefas**, inclusive as integradas sem rejeição, com uma linha por tentativa.

A decisão está em [ADR 0031](adr/0031-o-diario-e-uma-projecao-do-log-fiel-ao-que-foi-escrito.md); o plano, em [plano-diario-de-bordo.md](plano-diario-de-bordo.md).
