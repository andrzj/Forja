# 0007. Job Object por chamada e identidade do processo

- Status: Aceito
- Data: 10/10/2026

## Contexto

A especificação previa um Job Object por execução. Com um só objeto, encerrar a árvore de uma ferramenta que estourou o tempo-limite encerraria também as outras, e as chamadas ficariam acopladas entre si.

## Decisão

Cada chamada do executor cria o seu Job Object, com encerramento ao fechar. No Windows o processo nasce suspenso, entra no objeto e só então é retomado, para não escapar dele. Fora do Windows, o equivalente é um grupo de processos. O início do processo é gravado como evento de progresso `process_started`, com o PID e o horário de criação. Na retomada, só se encerra o processo cuja identidade confere; o PID reutilizado por outro processo é deixado em paz.

## Consequências

- Descendentes de um processo que morreu não são alcançados pela identidade gravada; quem os cobre é o encerramento ao fechar do Job Object.
- Os ramos para sistemas POSIX existem, mas ainda não foram exercitados fora do Windows.
- O comando passa antes por `check_command_safety`: recusa argumentos grandes demais, caractere nulo e metacaracteres em `.cmd` e `.bat`.

Ver a especificação, seções "Contrato 2" e "Particularidades do Windows".
