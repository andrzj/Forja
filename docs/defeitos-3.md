# Defeitos plantados do incremento 3 (3a)

Escrito em 12/10/2026, **antes de qualquer execução da Forja** sobre estes repositórios. Estado: aguardando revisão do dono. Nada aqui foi rodado pela Forja.

Os repositórios ficam em `scripts\medicao\defeitos\<nome>\`. `scripts\medicao\verificar_defeitos.py` confere tudo o que este documento afirma (roda pytest de verdade, em cópias temporárias).

## Estrutura de cada repositório

| Caminho | Papel | Quem vê |
| --- | --- | --- |
| `repo\` | Repositório com o defeito, `pyproject.toml`, `src\<nome>\core.py` e `tests\test_<nome>.py` (3 testes visíveis que passam, com e sem o defeito) | A Forja |
| `descricao.txt` | Texto do defeito, para `forja corrigir` | A Forja |
| `criterios.json` | Critérios numerados no formato de `CriteriaBody` (`origin` = "task description") | A Forja |
| `corrigido\core.py` | Versão correta do módulo | Só nós |
| `referencia\test_referencia.py` | Teste bom de referência: falha com o defeito, passa com a correção | Só nós |
| `ruins\test_ruim_*.py` | Testes ruins que o gate deve rejeitar | Só nós |

Cada critério foi escrito de modo que **viola o defeito**: um teste honesto para ele falha no código atual. Critérios que o defeito já cumpre ficaram de fora, porque o gate exige que teste novo falhe.

## Os quatro defeitos

| Repo | Função | Defeito | Correção | Critérios |
| --- | --- | --- | --- | --- |
| `pager` | `paginate(items, page, size)` | Páginas deslocadas: `start = page * size` | `(page - 1) * size` | 1) página 1 devolve os primeiros itens; 2) a última página devolve o resto e pode ser menor; 3) todas as páginas juntas dão a lista original |
| `spans` | `overlaps(a, b)` | Intervalos fechados que só se tocam não se sobrepõem: `<` em vez de `<=` | `<=` | 1) intervalos que só dividem um extremo se sobrepõem; 2) o resultado não depende da ordem dos argumentos |
| `money` | `split(total_cents, parts)` | O resto da divisão se perde: `[total // parts] * parts` | `divmod`, o resto vai às primeiras partes | 1) as partes somam o total; 2) total menor que o número de partes é mantido (`split(2, 3) == [1, 1, 0]`); 3) os centavos extras vão às primeiras partes (`split(10, 3) == [4, 3, 3]`) |
| `slugs` | `slugify(text)` | Separadores viram hífens sem colapsar nem aparar | colapsa corridas e apara as pontas | 1) corrida de não-alfanuméricos vira um hífen; 2) sem hífen inicial; 3) sem hífen final |

## Testes de referência (o teste bom)

Um por repositório, em `referencia\test_referencia.py`, escrito à mão a partir dos critérios (2 a 3 testes cada). Verificado: **todos falham por asserção com o defeito e todos passam com a correção**. Os testes visíveis do repositório passam nos dois estados.

## Testes ruins (devem ser rejeitados)

Cinco por repositório, 20 no total, em `ruins\`. Cada um é copiado para `tests\` do repositório com o defeito e rodado sozinho.

| Arquivo | O que faz | Resultado com o defeito | Causa certa da rejeição |
| --- | --- | --- | --- |
| `test_ruim_sem_assercao.py` | Chama a função e não afirma nada | verde | passa no código com o defeito (gate vermelho, regra d) |
| `test_ruim_assert_true.py` | Chama a função e faz `assert True` | verde | idem |
| `test_ruim_nao_chama.py` | Importa a função, mas só afirma sobre uma lista local | verde | idem |
| `test_ruim_assercao_fraca.py` | Chama a função e afirma só o tipo ou o tamanho do retorno | verde | idem |
| `test_ruim_erro_importacao.py` | Importa de um módulo que não existe | erro de coleta | erro de coleta não conta como vermelho (pergunta 13) |

Verificado por `verificar_defeitos.py`: os 16 primeiros passam com o defeito e o quinto de cada repositório dá erro de coleta (`ERROR`).

## Casos que o gate vermelho/verde do 3a **não** cobre

Registrados para ninguém contar com eles:

- **Vermelho pelo motivo errado.** Um teste que falha com o defeito, mas por outra causa (um erro de tempo de execução no próprio teste, uma asserção sobre outra coisa que também falha). O gate só vê "falhou". Quem pega é a mutação (3b) e a verificação de que o teste passa depois da correção (verde na etapa do implementador).
- **Teste que falha e continua falhando.** Cai na etapa do implementador, que precisa chegar ao verde dentro das tentativas.
- **Cobertura rasa do critério.** O manifesto liga critério a teste, mas não prova que o teste verifica o critério por inteiro.
- **Refatoração** (testes de caracterização que passam por natureza). O gate vermelho não se aplica; fica para a mutação (3b).

## Como a aceitação do 3a usa isto

- Passo 9: cada `test_ruim_*.py` é apresentado ao gate como se fosse a saída do autor de testes; o resultado esperado é a coluna "Causa certa" acima.
- O teste de referência é apresentado como o teste do autor e deve ser aceito; depois, com ele congelado, o implementador (ou a `corrigido\core.py`, nos testes automáticos) deve chegar ao verde.
- Execução viva com o Claude Code nos dois papéis em ao menos 2 dos 4 repositórios (os 3 testes ruins e a referência **não** são mostrados ao agente).

## Para revisar

- Os quatro defeitos e as redações de `descricao.txt` e `criterios.json` estão claros e não induzem o teste?
- O conjunto de testes ruins basta, ou falta um tipo (por exemplo, teste que lê arquivo, teste dependente de ordem)?
