# 0030. O teste diferencial compara medianas e põe o caso instável em quarentena

## Contexto

A Especificação manda o gate 11 reprovar saída nova diferente da antiga para as mesmas entradas e regressão de tempo ou memória acima do limite, e que o mesmo mecanismo meça tempo, memória e I/O antes e depois. Não diz como lidar com saída que varia entre execuções, com ruído de tempo e de memória, com plataforma que não mede memória, nem qual limiar vale quando o caso não tem linguagem. O ADR 0029 fixou de onde vêm os casos; este fixa como são medidos e julgados.

## Decisão

- **A base roda cada caso duas vezes, e o caso instável vai inteiro para quarentena.** Se as duas execuções diferem em alguma saída pela regra do próprio caso, o caso não reprova nenhuma tentativa, mesmo que só uma saída varie. Se todos os casos ficam em quarentena, o resultado é “não se aplica”, nunca aprovação. É o critério da suíte instável do E2E (gate 6).
- **Cada tentativa roda o caso `runs` vezes (padrão 3) e o tempo e a memória são julgados pela razão entre medianas**, com `max_time_ratio` e `max_memory_ratio` (1,25). Razão e mediana, não valor absoluto nem média, porque uma execução numa máquina ocupada move um valor e não a mediana, e porque a máquina da base e a da tentativa são a mesma só dentro da execução.
- **A saída que difere é achado, uma vez por caso e saída, e a mensagem nunca traz o conteúdo.** Diz o byte, a linha e os tamanhos; a saída pode ter dado pessoal.
- **Memória é o pico da árvore de processos, lido do Job Object (`PeakJobMemoryUsed`), e só no Windows.** Medido com filhos de tamanho conhecido, é a soma concorrente da árvore; `PeakProcessMemoryUsed` é só o maior processo e deixaria passar árvore que espalha a memória. Em POSIX não foi construído (`RUSAGE_CHILDREN` é do processo da Forja inteiro): sem medida num dos lados, a memória não é julgada e o resumo diz; o valor é “sem medida”, nunca zero.
- **O limiar é o mais folgado entre as linguagens do projeto.** O caso não tem linguagem; usar o mais folgado evita reprovar por um limiar de linguagem que o caso não usa.
- **O caso roda como o E2E:** mesmo executor, ambiente filtrado e armadilha de proxy em loopback. A versão antiga e a nova não alcançam a rede.
- **Modo observação, com a política “registrar como premissa” para o que não se mediu**, como os demais gates novos, até a calibração dos limiares com dados de revisão.
- **I/O fica fora**, declarado no resumo.

## Alternativas

- *Um caso instável só perde a saída instável.* Mantém mais cobertura, mas o tempo e a memória de um caso que não é determinístico também não são comparáveis; quem quer o caso inteiro declara `ignore` ou `json` na saída que varia.
- *Média ou mínimo em vez de mediana.* A média carrega o outlier; o mínimo esconde regressão que só aparece em parte das execuções.
- *Limiar absoluto (segundos, megabytes).* Depende da máquina; a razão contra a própria base não.
- *`PeakProcessMemoryUsed`.* Mais simples, mas só vê um processo.
- *Auxiliar POSIX sem poder testá-lo.* Uma medida que não pude exercitar seria um número sem prova; ficou como pendência.

## Consequências

Um caso com saída que varia deixa de proteger a refatoração até alguém declarar a regra que o torna estável, e o resumo diz quais casos ficaram assim. Em Linux e macOS o gate só vê saídas e tempo. A base de tempo e de memória de cada caso tem só duas medidas. O diferencial custa `runs` execuções de cada caso em cada tentativa, inclusive nas etapas do documentador e do autor de testes extra. O uso está em `docs/guia/gates/teste-diferencial.md`; o plano, em `docs/plano-gate-11.md`.
