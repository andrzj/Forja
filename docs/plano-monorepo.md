# Plano: monorepo

Estado: plano, nada implementado. Decisão do dono (19/10): monorepo aprovado, plano antes de código.

## O que o código mostra hoje (lido em 21/10)

- `Detection.roots` existe (`core/adapters/language.py:80-86`) mas todo adaptador devolve `(".",)` e ninguém lê o campo. `AdapterRegistry.detect_all` descarta `roots`.
- `cli/detect.py:74-78` e `PipelineMeasurer._active` (`orchestrator/measurer.py:114-121`) olham só manifestos na raiz da worktree.
- Toda operação usa `OperationRequest(root=worktree)`. Nenhum método recebe uma sub-raiz.
- Cada adaptador assume o manifesto em `request.root`: `pyproject.toml`, `go.mod` (argv `./...`), `package.json` e `node_modules/` (TypeScript), exatamente uma `.sln` ou `.csproj` (C#), `pom.xml` ou `build.gradle[.kts]` e `gradlew` (Java). O Java guarda um único `_uses_gradle` para o repositório todo.
- Os parsers de Python, Go e TypeScript assumem saída relativa ao cwd. Os de C# e Java tiram o prefixo `ToolOutput.root` (= cwd do plano). Nada recoloca o prefixo de uma sub-raiz; com cwd em sub-raiz, os caminhos sairiam relativos a ela, não à worktree.
- Os leitores de relatório (`core/reports/reading.py::resolve_path`) devolvem caminhos relativos ao `root` que recebem.
- `core/dependencies.py` liga só `node_modules` da raiz; `is_dependency` testa só o primeiro segmento do caminho.
- `AdapterRegistry.for_file` e `classify` decidem por nome do caminho, sem noção de sub-raiz. `EachLanguage` e `layout.by_adapter` agrupam por linguagem.

## Decisões

1. **Unidade de execução: o projeto = (adaptador, base).** `base` é o diretório do manifesto, relativo à worktree em POSIX (`.` para a raiz). Um repositório com `go.mod` na raiz e `web/package.json` tem dois projetos.
2. **Arquivo vai ao projeto mais próximo.** Entre os projetos cujo `base` contém o arquivo, vence o `base` mais longo; empate entre linguagens no mesmo `base` resolve por `classify` (como hoje). Arquivo sem projeto ancestral segue o comportamento atual (adaptador que o classifica, `base` `.`).
3. **Adaptadores não mudam de contrato.** Um `ScopedAdapter(adapter, base)` implementa `LanguageAdapter` e faz a tradução na borda: `request.root` vira `worktree/base`; `request.files` perdem o prefixo `base/`; todo caminho nos resultados (build, teste, lint, formato, cobertura, mutação, complexidade) ganha o prefixo `base/`. Com `base == "."` é identidade. Os checks continuam vendo caminhos relativos à worktree.
4. **Uma instância de adaptador por projeto.** Resolve o `_uses_gradle` do Java sem tocar no adaptador.
5. **Detecção por varredura.** Ajudante único em `core/adapters/` percorre a worktree, ignora `node_modules`, `.git`, `target`, `vendor`, `bin`, `obj` e diretórios ocultos, e devolve os diretórios com cada manifesto. Os cinco `detect` e `cli/detect.py` usam o mesmo ajudante, e `Detection.roots` passa a ser preenchido de verdade.
6. **Manifesto aninhado dentro de projeto da mesma linguagem** (pacote dentro de pacote): cada um é um projeto; o mais próximo vence (decisão 2). Não há herança de configuração do pai.
7. **Dependências por projeto.** `node_modules` é ligado em cada `base` de projeto TypeScript que o tem no repositório; `is_dependency` passa a reconhecer `node_modules` em qualquer nível; `stage_all` usa pathspec que exclui em qualquer nível.
8. **Raiz de testes e congelamento.** `_test_root` hoje vale `tests` só se Python é a única linguagem. Em monorepo fica vazio e o congelamento segue só pelos arquivos que os adaptadores classificam `TEST`/`FIXTURE` (mecanismo do passo 4 da generalização, já existente).

## Passos (um commit cada)

1. **Detecção e projetos.** Ajudante de varredura; `detect` dos cinco adaptadores preenche `roots` e `manifests`; `cli/detect.py` e `check_repository` usam a varredura. Teste: monorepo de diretórios temporários com Go + TypeScript + Java, `node_modules` e `target` ignorados.
2. **`ScopedAdapter` e registro por projeto.** `AdapterRegistry` guarda projetos; `for_file` aplica a decisão 2. Teste de tradução (`root`, `files`, prefixo nos caminhos) por tipo de resultado. Antes de escrever, ler os tipos de resultado de cada operação em `core/adapters/` e `core/reports/`; este plano não os viu por inteiro.
3. **Pipeline por projeto.** `_active`, `EachLanguage`, `layout.by_adapter`, `_files_of` e `_texts_of` passam a chave (linguagem, base). Mutação, CRAP e cobertura rodam uma instância por projeto. A cópia da worktree para o lint "antes" e para a mutação continua inteira.
4. **Dependências por projeto** (decisão 7). Testes em `tests/core/test_dependencies*`.
5. **Verificação por adaptador.** Para cada linguagem, rodar a ferramenta real numa sub-pasta e conferir que os caminhos voltam relativos à worktree: Python (`coverage.json` relativo), Go (`./...` e `.forja-cover.out`), TypeScript (`tsc -p .`, `node_modules`), C# (uma `.sln`/`.csproj` por sub-pasta), Java (Maven e Gradle). Corrigir só o que falhar.
6. **Ponta a ponta** com um monorepo pequeno (Go na raiz mais TypeScript em subpasta, ou o par que as ferramentas instaladas permitirem), no molde de `tests/checks/test_real_languages.py`. Gate de mutação no WSL nos arquivos novos.

## Limites já conhecidos

- C# exige exatamente uma `.sln` ou `.csproj` no `base`; mais de uma no mesmo diretório continua `NotSupported`.
- `go.work` não é tratado: cada `go.mod` é um projeto isolado.
- `cli/detect.py` e a varredura leem o disco inteiro da worktree uma vez; custo aceito.
- Projeto cujo arquivo mudado é só de configuração de outro projeto não é associado a ele.

## Estado

Plano escrito em 21/10. Próximo: passo 1.
