# Plano: dependências que o agente pode adicionar (fila 11)

Ordem do dono (31/10/2026): um agente que escreve código tem de poder usar pacotes externos; a regra é não trazer dependência que não seja necessária (DRY: biblioteca padrão e o que o projeto já declara primeiro). Decisão do dono sobre o Python: **ambiente virtual isolado por execução**.

## Situação lida no código

- `ScopeCheck._implementer` recusa todo arquivo que o adaptador não classifica como produção. O manifesto (`pyproject.toml`, `go.mod`, `pom.xml`, `package.json`, `*.csproj`) é "outro", então nenhuma dependência chega a existir (visto na execução real 5, três recusas).
- Os modelos de instrução do implementador (`INSTRUCTIONS`, `FIX_INSTRUCTIONS`) dizem "do not add dependencies".
- O gate 10 já tem o detector (`checks\new_dependency.py`: existência no registro, idade, uso) e o ADR por dependência já dispara (`_adr_triggers`). Falta só o caminho até eles.
- O Python roda os testes com o interpretador do repositório (`cli\session.py::repo_python`: `.venv` ou `venv` do repositório, senão o `python` do PATH). Dependência nova não está instalada nele. Go, Java, TypeScript e C# resolvem as dependências pela própria ferramenta.

## Passos (um commit por passo)

1. **Gate 1 aceita manifesto.** `ScopeCheck` recebe `is_manifest` (de `new_dependency.is_manifest` sobre `manifests_of`). Implementador e autor de testes podem mudar arquivo de manifesto; nada mais que o gate recusava passa a passar. Lockfile fica de fora (o agente não instala).
2. **Instruções.** Sai "do not add dependencies" dos modelos do implementador e do autor de testes; entra a regra: biblioteca padrão e o que o projeto já declara primeiro, dependência nova só se indispensável, uma por necessidade, e o `reason` da ação diz por que nada existente serve.
3. **Existência antes da instalação (Python).** Antes de instalar, a Forja confere cada dependência nova no registro (`look_up` do `new_dependency`). Inexistente ou inalcançável: a tentativa é rejeitada com o achado do gate 10, sem instalar nada.
4. **Ambiente virtual por execução (Python).** `languages\python\environment.py`: cria `<workdir>\venv` com o `python` do repositório, deixa visíveis os pacotes desse interpretador (arquivo `.pth` que chama `site.addsitedir` no `site-packages` dele, atrás dos do ambiente novo; assim as instalações editáveis também aparecem) e instala nele as dependências declaradas no manifesto. A instalação é do que o manifesto da cópia declara a mais do que já foi instalado. O adaptador passa a usar o `python` do ambiente. O ambiente da Forja e o do repositório não são tocados.
5. **Ligação.** `cli\session.py` e `orchestrator\measurer.py`: o ambiente é criado na medição da base, atualizado a cada tentativa cujo manifesto mudou, e descartado ao fim da execução. Instalação que falha vira rejeição da tentativa com o erro do instalador.
6. **Testes, documentação, ADR e rodada real.** Testes por passo; `docs\guia\gates\seguranca-e-dependencias.md` e ADR 0036; execução real `criar` com `python-slugify`; gate de mutação nos arquivos novos.

## Limites declarados

- Instalar pacote executa código do pacote (scripts de construção). A Forja não cria sandbox (ADR 0018); a instalação roda no ambiente do usuário, como o resto, só depois da verificação de existência, idade e uso do gate 10.
- Só o Python tem passo de ambiente. Nas outras linguagens a dependência nova passa pelo gate 1 e pelo gate 10, e a ferramenta da linguagem a resolve na hora de construir e testar; não há E2E dessas linguagens nesta fila.
- A idade e o uso da dependência (gate 10) julgam depois da instalação; a existência julga antes.
