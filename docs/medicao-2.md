# Incremento 2 — medição contra a linha de base: protocolo

Este documento fixa o experimento **antes** de qualquer execução, como pede o plano ("critérios de sucesso definidos antes"). Os números só entram em `medicao-2-relatorio.md`, depois.

## Pergunta

Para a mesma tarefa de refatoração, a Forja (portões, tentativas guiadas, integração por tarefa) entrega mais trabalho correto, com menos regressões e a um custo aceitável do que a mesma CLI com um único prompt?

## Tarefas

Só existe o objetivo "refatorar" (reduzir a complexidade de funções acima de 15 sem mudar o comportamento), então é o único medido.

| Repositório | Papel | O que tem |
| --- | --- | --- |
| `plain`, `shop`, `web` (os três da aceitação do 1h) | controle | uma função com cadeia de `elif`; qualquer braço deve acertar |
| `inventory` | tarefa média | vários módulos, 3 funções acima de 15 com armadilhas: exceções com tipo e mensagem, ordem de efeitos colaterais, arredondamento, argumento mutável |
| `scanner` | tarefa média | leitor de um formato de configuração, máquina de estados e expressões regulares; 3 funções acima de 15 |

Cada repositório nasce de um commit fixo, com testes visíveis que passam. As ferramentas (ruff, lizard, gitleaks, pytest) são as mesmas nos dois braços.

## Braços

Nos dois: mesmo Claude Code, mesma versão e mesmo modelo, mesmo commit inicial, mesmo escopo (o repositório inteiro), mesmo teto de 200 mil tokens por execução (decidido pelo dono em 12/10; uma execução que passe do teto não é aceita).

- **A, só prompt.** `claude -p` na raiz de uma cópia do repositório, com um prompt único e fixo (abaixo), ferramentas de arquivo e os comandos `python -m pytest` e `python -m ruff` liberados. Sem portões, sem tentativas guiadas, sem retomada. O que o agente deixar na cópia é a entrega.
- **B, Forja.** `forja refatorar` com o `forja.toml` do repositório, `agente_roda_testes` ligado (o padrão), 5 tarefas, 3 tentativas. A entrega é a branch `forja-run/...`; sem branch integrada, nada foi entregue.

Prompt do braço A, sem variação entre execuções:

> Reduza a complexidade ciclomática de toda função deste repositório que esteja acima de 15, sem mudar o comportamento: mesmos resultados, mesmos nomes públicos, mesmos efeitos. Não altere testes nem dependências. Rode os testes e o ruff ao terminar e deixe tudo passando.

## Repetições

3 por repositório e braço: 5 × 2 × 3 = 30 execuções. A ordem é embaralhada e fixa por uma semente registrada.

## Quando uma entrega é aceita

Critério objetivo, aplicado de fora aos dois braços sobre a árvore final, por um script que nenhum braço vê:

1. compila (`compileall`);
2. os testes visíveis passam;
3. `ruff format --check` e `ruff check` sem erro novo em relação ao commit inicial;
4. `gitleaks` sem achado novo;
5. cada função alvo ficou com complexidade 15 ou menos (lizard) e nenhuma função passou de 15 que antes não passava;
6. só arquivos de código-fonte do repositório mudaram (nenhum teste, nenhuma dependência).

Execução sem alteração, sem branch integrada (código de saída 4 da Forja) ou que estourou o teto de tokens não é aceita.

## Regressão

Para cada repositório médio (`inventory`, `scanner`), testes de caracterização com saídas gravadas do **código original** em uma grade de entradas (valores comuns, limites, vazios, tipos errados, exceções), guardados fora do repositório e nunca mostrados a nenhum braço. Uma entrega é regressão se algum deles falhar na árvore final, mesmo que ela passe nos testes visíveis. Conta-se por execução (houve ou não) e por caso falho.

Os controles não têm oráculo oculto: neles a regressão é só a falha dos testes visíveis, que já reprova a entrega.

## O que se mede por execução

Aceita ou não (e qual item falhou), regressão (sim ou não, casos que falharam), tempo total, número de tentativas (A conta uma; B, as da Forja), tokens enviados e escritos (leitura de cache fora, como na Forja).

## Decisão (fixada antes)

A ordem de avaliação é esta; vale a primeira que se aplicar.

1. **Inconclusivo:** os dois braços têm taxa de aceitação de pelo menos 90% e nenhuma regressão nas execuções das tarefas médias. As tarefas são fáceis demais para separar os braços (efeito teto) e nada se conclui sobre a tese. Segue uma segunda rodada com tarefas mais difíceis (repositórios maiores ou funções com mais armadilhas), com o protocolo registrado antes, e o dono decide.
2. **Seguir:** taxa de aceitação da Forja pelo menos 15 pontos percentuais acima da linha de base, regressões da Forja menores ou iguais às da linha de base, e tokens da Forja no máximo 2× os da linha de base.
3. **Ajustar:** a Forja vence em aceitação e regressões, mas custa mais de 2×; ou vence em um dos dois e empata no outro.
4. **Parar:** a Forja não vence em aceitação nem em regressões, e ao menos um braço ficou abaixo de 90% de aceitação ou teve regressão.

Os controles não entram na taxa de decisão, só aparecem no relatório (se algum braço errar um controle, isso é um achado por si só). A decisão final é do dono do repositório; quem mede apresenta os números e uma recomendação.

Esta regra do "inconclusivo" foi acrescentada em 12/10, depois do piloto e antes de qualquer execução contada, ao se ver que uma única execução média já era aceita nos dois braços.

## Piloto (fora dos números)

Uma execução de cada braço no controle `plain` e no `inventory` (repetição 0, excluída do relatório): `plain` A 9.486 tokens em 22 s e B 7.256 em 27 s; `inventory` A 20.788 tokens em 67 s (1 tentativa) e B 30.521 em 76 s (3 tentativas). Os quatro foram aceitos, sem regressão. Estimativa das 30 execuções: cerca de 470 mil tokens e 40 minutos.

## Limitações declaradas

- O mesmo autor construiu a Forja e escreveu as tarefas; as tarefas médias foram escritas antes de rodar qualquer braço, mas isso não elimina o viés. Por isso o oráculo de regressão é gravado do código original, não escrito à mão.
- 15 execuções por braço dão pouca força estatística: o relatório mostra os números brutos e não afirma significância.
- Só Python, só refatoração, só Claude Code, em uma versão do modelo. A conclusão não vale além disso.
- A revisão "às cegas" é feita por critério objetivo, não por pessoa; se o dono quiser revisar entregas à mão, o script guarda a árvore final de cada execução sem dizer o braço.

## Custo

Medido no piloto (seção acima) e aprovado pelo dono: teto de 200 mil tokens por execução, cerca de 470 mil esperados no total.

## Entregas deste incremento

`scripts/medicao/` (repositórios, oráculo, avaliador e executor, fora do produto), `docs/medicao-2-relatorio.md` e `docs/adr/0019-...md` com a decisão.
