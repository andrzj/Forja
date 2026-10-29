# Plano: lint, formato, build e testes do pipeline em todas as linguagens; congelamento por arquivo

Origem: decisão do dono em 19/10 (não é opcional). Pendências em `NOTAS.md`, seções 4 e 7. Estado: **aguardando aprovação do dono; nenhum código escrito.**

## O que o código faz hoje (visto)

- `PipelineMeasurer` recebe **um** adaptador, e `cli/session.py:264` monta sempre `PythonAdapter`.
- `checks/layout.py:14`: `SOURCE_SUFFIXES = (".py", ".pyi")`. `FormatCheck` e `LintCheck` filtram `changes.current(SOURCE_SUFFIXES)`; sem `.py` mudado, aprovam sem rodar nada.
- `measurer.py` usa `SOURCE_SUFFIXES` em `_production_files` (linha 226) e em `read_before` (256, 261), que alimentam complexidade, CRAP e o "antes" do lint.
- `BuildCheck`, `TestsCheck`, `MutationCheck`, `CrapCheck` já pedem tudo ao adaptador (`plan`/`parse`); só estão ligados ao Python porque só existe um adaptador no measurer.
- `AdapterRegistry` (`core/adapters/registry.py`) já tem `detect_all(root)` e `classify(path)`; ninguém o usa na sessão.
- Congelamento: `tree_digest(worktree, test_root)` (`checks/freeze.py`) cobre um diretório. `FreezeCheck`/`AppendOnlyCheck` e `TaskInfo.test_root`/`frozen_digest` dependem dele. O escopo do autor de testes (`ScopeCheck`, `scope.py:122`) também é por diretório.
- `checks/structure` (pass-through, profundidade) já escolhe a linguagem pelo sufixo, não pelo adaptador.

## Decisões de desenho

1. **Vários adaptadores no measurer.** `PipelineMeasurer(adapters=...)` no lugar de `adapter=`. Um `AdapterSet` pequeno (em `core/adapters/`, junto do registry) expõe: `for_file(path)` (o adaptador que classifica o arquivo), `detected(root)` (os adaptadores com manifesto na raiz) e `classify(path)`. Sem mudar o `Protocol` `LanguageAdapter` nem `CONTRACT_VERSION`.
2. **Sufixo sai, classificação entra.** Trocar `SOURCE_SUFFIXES` por "o adaptador classifica o arquivo como `PRODUCTION`, `TEST` ou `FIXTURE`". Quem decide o que é código-fonte da linguagem é o adaptador, não uma lista no check.
3. **Format e lint por adaptador.** `FormatCheck`/`LintCheck` agrupam os arquivos mudados por adaptador e rodam uma operação por grupo; os achados se somam. Lint "antes" idem, por grupo, copiando para o diretório privado os arquivos de configuração que cada adaptador declara (hoje `LINT_CONFIG` é fixo do ruff). Preciso de um acessor novo no adaptador, `lint_config_files`, **fora do `Protocol`** (atributo opcional lido com `getattr`, padrão vazio), para não mexer no contrato.
4. **Build e testes por adaptador detectado.** `BuildCheck`/`TestsCheck` rodam para cada adaptador detectado na raiz; reprova se qualquer um reprova. Os ids de teste já vêm do `parse` de cada adaptador; a quarentena e `passing` seguem por id de teste (os ids de linguagens diferentes não colidem: caminho do arquivo/pacote no id).
5. **Congelamento por arquivo.** `frozen_digest` passa a ser o digest do conjunto de arquivos que o `classify` dá como `TEST`/`FIXTURE` (mais tudo sob `test_root`, quando houver), não de um diretório. `tree_digest(worktree, root)` vira `tests_digest(worktree, files)` sobre a lista de `git ls-files` classificada. `FreezeCheck` e `AppendOnlyCheck` testam "o arquivo é de teste" em vez de "está sob `test_root`".
6. **Escopo do autor de testes.** `ScopeCheck` passa a permitir ao autor de testes escrever em arquivos classificados `TEST`/`FIXTURE`; sob `test_root` quando `[tests] root` estiver definido (compatível com o Python de hoje). O autor não escreve em produção; o implementador não escreve em teste (já é assim por classe de arquivo).
7. **`test_root` vira opcional.** Python mantém `tests`; Go, JS/TS, C# e Java declaram `test_root = ""` (testes ao lado do código ou em árvore própria do projeto). `FixPlanner` e `agent_runner` hoje escrevem "só sob `{test_root}`": com raiz vazia, dizem "só arquivos de teste da linguagem".
8. **Estrutura (pass-through, profundidade) e complexidade** já leem várias linguagens por sufixo; só trocar o filtro de `_production_files`/`read_before` pela classificação (decisão 2). O `lizard` suporta as seis linguagens; sem mudança de ferramenta.
9. **`cli/session.py`:** montar o `AdapterSet` com os cinco pacotes de `forja.languages` (nota: `repo_python(repo)` continua só para o Python) e deixar o `AdapterSet.detected` escolher. Se nenhum adaptador for detectado, falha com configuração inválida (saída 2), como hoje faz um repositório sem manifesto.
10. **Nenhum adaptador instala ferramenta** (decisão anterior); a ferramenta ausente continua `Inconclusive`/`doctor`.

## Ordem de execução (um passo por sessão, cada um com testes só do que é criado)

1. `AdapterSet` + trocar o filtro por sufixo pela classificação em `layout.py` e `measurer.py`; `PipelineMeasurer` aceita vários adaptadores. Testes com dois adaptadores falsos (Python + Go).
2. `FormatCheck`/`LintCheck` por grupo de adaptador, com `lint_config_files`.
3. `BuildCheck`/`TestsCheck` por adaptador detectado; `session.py` monta o conjunto.
4. Congelamento por arquivo (`tests_digest`, `FreezeCheck`, `AppendOnlyCheck`, `ScopeCheck`, `test_root` vazio, textos do `agent_runner`).
5. Ponta a ponta por linguagem com ferramentas reais (Go, JS/TS, C#, Java): um reparo mínimo cruzando formato, lint, build, testes, congelamento e mutação; os testes pulam sem a ferramenta, como os de mutação.
6. Gate de mutação (`scripts\mutate.py`, WSL) nos arquivos reescritos: `layout.py`, `freeze.py`, `scope.py`, `build_and_tests.py`, `measurer.py`, `registry`/`AdapterSet`, `task_cycle.py`. Atualizar `docs\Especificação.md` e `docs\estado.md`.

## Risco e limite

- Repositório com duas linguagens roda as ferramentas das duas a cada tentativa: mais lento. Aceito; o cache de medições (3e) foi suprimido por ordem do dono em 29/10/2026; o custo real se vê com a Forja em uso.
- Dois arquivos de teste de linguagens diferentes com o mesmo id: a quarentena os trata como o mesmo teste. Improvável (id leva o caminho); registrado, não tratado.
