# 0031. O diário é uma projeção do log, fiel ao que foi escrito

## Contexto

O agente de cada tentativa recebia só a última rejeição da etapa. Duas tentativas que partiam da mesma hipótese e falhavam no mesmo gate se repetiam sem que o agente nem a Forja vissem o padrão, e o revisor só via o motivo final de cada rejeição. A avaliação da skill `ub-mode` (`unclebob/ub-mode`, “Keep a Log” e “Attack the Premise”) mostrou que esse era o que a Forja não tinha.

## Decisão

- **O diário é uma projeção do log de eventos e não grava estado novo.** Lido do `RunState`, como o resumo: a execução retomada, ou o log cortado na última linha, dá o mesmo texto. Não há evento novo nem campo novo no contrato de saída do LLM.
- **Toda entrada ao modelo é fiel, fidedigna e verdadeira** (ordem do dono, 28/10/2026). A fala do agente e o motivo não são cortados nem reescritos, e texto de várias linhas vai citado com `> `. Os cortes que existem (linha única de 160 caracteres, teto de 6000, queda das tentativas mais antigas) são determinísticos e o texto os declara, com a contagem do que ficou de fora. Nenhum LLM resume o diário.
- **O agente vê as tentativas anteriores da mesma etapa**, antes da rejeição mais recente, que segue sendo a última seção do pacote. O trecho passa pelo redator.
- **Duas rejeições da etapa no mesmo `gate N (check)` pedem a hipótese.** O texto é “Attack the Premise” com “hypothesis” no lugar de “premise”, porque `Assumption` e `PREMISE` já têm outro sentido na Forja. A hipótese é escrita no `reason` da ação; a Forja não confere.
- **O ramo da tarefa leva uma cópia**, `docs/mudancas/<tarefa>-diario.md`, escrita pela Forja no commit `docs:` do documentador, ao lado do registro de mudança. O documentador não escreve esse arquivo; o escopo só aceita o da própria tarefa. As tentativas rejeitadas continuam sem commit de código.
- **A cópia do ramo não é redigida**, como o corpo do commit, que já leva a fala do agente: a redação cobre o que a Forja envia a terceiros (ADR 0009) e a Forja nunca faz push (ADR 0013). O id da tarefa é `t<número>`, gerado pela Forja, então o nome do arquivo não colide com o de outro registro.

## Alternativas

- *Evento novo de diário no log.* Duplicaria o que o log já diz e criaria um segundo caminho de escrita para reconciliar na retomada.
- *Resumir a fala do agente com um LLM, ou cortá-la em 300 caracteres.* Cortaria o que importa (a hipótese cabe no fim do texto) e daria ao modelo uma entrada que não é a que foi escrita.
- *Campo `hypothesis` no contrato de saída.* Mudaria o contrato de todos os papéis por uma instrução que a Forja não consegue conferir de qualquer modo.
- *Diário só no resumo, sem cópia no ramo.* O revisor que lê a branch não veria o que foi tentado.
- *Redigir a cópia do ramo.* Mudaria o texto que o revisor lê sem que o corpo do commit, com a mesma fala, mudasse junto.
- *Guardar o diário entre execuções.* Fora de escopo; cada execução tem o seu, como os fatos.

## Consequências

O agente gasta mais contexto a partir da segunda tentativa (até 6000 caracteres). A seção de hipótese pede uma frase que ninguém confere. O ramo ganha um arquivo por tarefa, com a fala do agente sem redação. Papel e CLI não aparecem por entrada. O uso está em `docs/diario-de-bordo.md`; o plano, em `docs/plano-diario-de-bordo.md`.
