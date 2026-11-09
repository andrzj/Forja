# Diário de bordo

Cada chamada a um agente é nova. Sem ajuda, o agente de uma tentativa só saberia da última rejeição, e ninguém veria o padrão de duas tentativas que partem da mesma hipótese e falham no mesmo gate. O diário de bordo é o histórico das tentativas de uma tarefa, mostrado ao agente, a você no resumo e ao ramo da execução.

Não há configuração: nem o `forja.toml` nem o `execucao.toml` têm chave para o diário, e ele vale em toda execução. Os comandos que geram execuções estão em [comandos.md](comandos.md).

## O que é

O diário é lido do registro de eventos da execução. A Forja não guarda nada a mais. Uma execução retomada, ou um registro cortado na última linha, produz o mesmo texto.

Cada entrada é uma tentativa e traz:

- **o que o agente disse**: o texto que ele deu ao terminar, no campo `reason` da sua ação, exatamente como foi guardado;
- **o desfecho**: rejeitada (com o gate e os achados), aprovada (com os gates que passou), descartada (com o motivo; a falha de infraestrutura é marcada) ou não terminou;
- **o que a Forja decidiu**: etapa esgotada e tarefa bloqueada, cada uma com o motivo.

O texto do agente e o motivo da rejeição não são resumidos, cortados nem omitidos, e nenhuma tentativa fica de fora. Texto de várias linhas vai citado, com `> ` no início de cada linha, para não se passar por título ou seção.

Tentativas rejeitadas continuam sem commit de código. O diário as registra só como texto.

## Onde ele aparece

| Onde | O que mostra | Quando |
| --- | --- | --- |
| `.forja-agent/diary.md`, na cópia de trabalho do agente | todas as tentativas anteriores da mesma etapa, cada uma inteira | a partir da segunda tentativa da etapa |
| pacote do agente, seção "Earlier attempts of this stage" | ordem de ler o arquivo acima antes de agir | quando o arquivo existe |
| pacote do agente, seção "The previous attempt was rejected" | o motivo da última rejeição e, abaixo, o que o agente disse naquela tentativa | quando a tentativa anterior foi rejeitada |
| pacote do agente, seção "Attack the hypothesis" | pedido para escrever a hipótese em uma frase no `reason` | veja "Hipótese comum a rejeições repetidas" |
| `resumo.md` da execução, seção "Diário de bordo" | por tarefa, cada tentativa com o que disse e o motivo, e as decisões da Forja | sempre |
| ramo da tarefa, `docs/mudancas/<tarefa>-diario.md` | todas as tentativas de todas as etapas da tarefa, e as decisões | no commit `docs:` do documentador |

Os títulos das seções do pacote ficam em inglês porque o pacote inteiro é escrito em inglês para o agente.

### Arquivo do agente

O arquivo `.forja-agent/diary.md` tem uma entrada por tentativa anterior, no formato `### Attempt <id>: rejected` (ou `approved`, `discarded`, `discarded (infrastructure)`, `did not finish`), seguida de "You said" e "Why", quando há texto.

O agente não pode editar o arquivo. Nas CLIs que aceitam regras de permissão (`claude-code` e `grok`) a edição é negada. Em todas, a Forja confere ao receber o trabalho que o arquivo é idêntico ao gravado; se mudou ou sumiu, o trabalho é rejeitado. Detalhes da cópia de trabalho em [ambiente.md](ambiente.md).

O arquivo passa pelo redator, o mesmo do README e dos fatos: segredos são mascarados e o resto do texto fica inteiro. Se o redator retirar o conteúdo, o arquivo diz que as tentativas anteriores foram retidas, com o motivo.

### Resumo da execução

A seção "Diário de bordo" do `resumo.md` lista, por tarefa, uma linha por tentativa, inclusive de tarefas integradas sem nenhuma rejeição, e uma linha por decisão da Forja. Cada linha tem o id da tentativa, o desfecho, `disse:` e `motivo:`. Para tentativa aprovada não há `motivo:`. Só o espaço em branco entre as palavras vira um espaço, para caber em uma linha. Sem nenhuma tentativa, a seção diz "Nenhuma tentativa." O resumo não vai ao modelo e não é commitado.

```text
- `t1` (corrigir o frete grátis):
  - `a1` rejeitada; disse: ajustei o limite; motivo: gate 5 (tests): 2 testes falham
  - `a2` aprovada; disse: limite passou a ser maior ou igual a 100
```

### Ramo da tarefa

O arquivo `docs/mudancas/<tarefa>-diario.md` é escrito pela Forja junto com o registro de mudança, no commit `docs:` da tentativa do documentador. Traz, em Markdown, todas as tentativas de todas as etapas da tarefa, as rejeitadas inclusive, e as decisões, tudo citado e sem corte. Cada tentativa vira um título "Tentativa `<id>` da etapa `<etapa>`" com o desfecho, "Disse" e "Motivo" (ou "Gates aprovados" quando aprovada). Decisões vêm como "Decisão da Forja". Sem nada a registrar, o arquivo diz "Nenhuma tentativa anterior."

A tentativa do documentador que está sendo julgada fica de fora do arquivo. O arquivo também passa pelo redator, como o do agente. O corpo do commit, que traz a fala do agente, não passa por ele.

Os arquivos de `docs/mudancas/` são da Forja. A verificação de escopo rejeita o documentador que mexe em qualquer registro de `docs/mudancas/` além dos desta tarefa, e a Forja grava o texto final por cima.

## Hipótese comum a rejeições repetidas

Quando duas ou mais tentativas da mesma etapa foram rejeitadas no mesmo gate e check, a próxima recebe no pacote a seção "Attack the hypothesis". Ela pede que o agente escreva, em uma frase no `reason` da ação, a hipótese que as correções compartilham, antes de tentar outra correção. O texto é fixo.

Só conta a rejeição cujo motivo começa com `gate N (check)`, com o mesmo par nas duas. Descarte por infraestrutura e rejeições que não vêm de um gate (por exemplo, trabalho que tocou onde não podia) não contam.

## O que o diário não faz

- **Não confere a hipótese.** A Forja pede que ela seja escrita no `reason`, mas não verifica que foi.
- **Não guarda nada entre execuções.** Cada execução tem o seu.
- **Não registra papel nem CLI por entrada.** O registro de eventos guarda só o sufixo do id da etapa, e a CLI vem da configuração.
- **Não bloqueia pela voz.** O gate de voz e o de comentários nunca bloqueiam, também sobre este arquivo.
