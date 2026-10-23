# Segurança e dependências (gate 10)

O gate 10 tem três checks: `sast`, `dependency_audit` e `new_dependency`. Os três nascem em **modo observação**: o resultado aparece no resumo, mas não bloqueia a tarefa até você promovê-los (veja o fim deste documento).

Dois deles dependem de algo que **você fornece**. A Forja não traz regras do Semgrep nem lista de licenças (ADR 0024). Sem o que é seu, o check não executa, e o resumo da preparação e o da entrega dizem isso em destaque.

## SAST com o Semgrep

O que o check faz: roda o Semgrep nos arquivos que a tentativa mudou e, numa cópia da árvore devolvida ao commit pai, nas versões antigas. Só reprova o que **aumentou** por arquivo e regra; achado que já existia não conta.

### Instalação

O `semgrep` precisa estar no PATH (`pip install semgrep`, ou veja a documentação oficial em <https://semgrep.dev/docs/getting-started/cli>). O `forja doctor` pede o `semgrep` quando há regras configuradas. Os testes desta versão usaram o Semgrep 1.182.1.

### De onde vêm as regras

Em ordem de precedência:

1. `--semgrep-config CAMINHO` na linha de comando (arquivo ou diretório local).
2. A chave `semgrep_config` do `execucao.toml`.
3. `.semgrep.yml` ou o diretório `.semgrep/` na raiz do **commit base** do repositório.

Regras de registro (`auto`, `p/...`, `r/...`, `s/...`, `semgrep.dev/...` ou URL) são recusadas com erro de configuração (código de saída 2): a Forja só usa regras locais, para não depender da rede nem de conteúdo que você não revisou.

A Forja copia as regras para fora da cópia de trabalho do agente no início da execução. Editar o arquivo de regras numa tentativa não muda o que é escaneado, e o gate de escopo rejeita a mudança de qualquer arquivo que não seja código de produção.

### Sem regras

Sem configuração o check devolve “não aplicável” e o resumo diz **“SAST NÃO EXECUTADO”**. Nunca é uma aprovação.

### Exemplo mínimo

A Forja nunca usa este exemplo sozinha; ele só mostra o formato. Salve como `.semgrep.yml` na raiz do repositório e faça commit (as regras são lidas do commit base):

```yaml
rules:
  - id: shell-true
    pattern: subprocess.$FUNC(..., shell=True, ...)
    message: "shell=True permite injeção de comando"
    languages: [python]
    severity: ERROR
```

Para escrever as suas, use a documentação do Semgrep: <https://semgrep.dev/docs/writing-rules/overview>. O Semgrep cobre Python, JavaScript, TypeScript, Go, Java e C#.

### Se o Semgrep falha

Código de saída diferente de 0 (por exemplo, 7 para um diretório de regras vazio), relatório ilegível ou o programa ausente dão resultado **inconclusivo**, nunca aprovação. Se roda nos arquivos novos mas não nos antigos, também é inconclusivo.

## Vulnerabilidades e licenças (OSV-Scanner)

O check `dependency_audit` só roda quando um arquivo de dependências que o OSV-Scanner lê foi alterado:

| Linguagem | Arquivos |
|---|---|
| Python | `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pdm.lock`, `uv.lock`, `pylock.toml` |
| JavaScript/TypeScript | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` (o `package.json` **não** é lido pelo OSV) |
| Go | `go.mod` |
| Java | `pom.xml`, `gradle.lockfile`, `buildscript-gradle.lockfile` |
| C# | `packages.lock.json`, `packages.config`, `deps.json` |

Ele roda o `osv-scanner` no estado novo e, numa cópia com os textos do commit pai, no antigo. Reprova a combinação (pacote, versão, vulnerabilidade) que existe só no novo. Precisa do `osv-scanner` no PATH (<https://google.github.io/osv-scanner/>) e de **rede** (vulnerabilidades e licenças vêm de serviços online). O `osv-scanner` resolve também dependências transitivas de alguns arquivos, então o achado pode ser de um pacote que o arquivo não nomeia.

### Licenças proibidas

Você fornece a lista no `forja.toml` do repositório, com identificadores SPDX:

```toml
[licenses]
forbidden = ["GPL-3.0-only", "AGPL-3.0-only"]
```

As listas de várias camadas (perfil, repositório) se somam. A comparação ignora maiúsculas e minúsculas, e uma licença proibida conta mesmo dentro de uma expressão (`MIT OR GPL-3.0-only` reprova, mesmo havendo uma opção permitida).

Sem a lista, só as vulnerabilidades são auditadas, e o resumo diz **“Licenças não verificadas”**. Pacote sem licença conhecida (`UNKNOWN`, `non-standard`, `NOASSERTION` ou lista vazia) é **inconclusivo** quando a lista existe. Se o OSV-Scanner conta uma licença proibida no resumo da varredura e nenhum pacote listado a tem, o resultado também é inconclusivo.

## Dependência nova inexistente ou suspeita

O check `new_dependency` olha o que o manifesto novo tem a mais que o antigo e consulta o registro oficial do ecossistema:

| Ecossistema | Manifestos lidos | Registro |
|---|---|---|
| Python | `pyproject.toml` (dependências, extras e grupos), `requirements*.txt` | PyPI |
| JavaScript/TypeScript | `package.json` (só o que vem do registro; `file:`, `git`, URL e `workspace:` ficam de fora) | npm |
| Go | `go.mod` | proxy do Go |
| Java | `pom.xml`, `build.gradle[.kts]` (notação `"grupo:artefato:versão"`) | Maven Central |
| C# | `*.csproj`, `Directory.Packages.props`, `packages.config` | NuGet |

Reprova o pacote que **não existe** no registro, que foi publicado há menos de `min_age_days` dias ou que tem menos de `min_downloads`. Os padrões são 30 dias e 100 downloads, e você muda por linguagem:

```toml
[checks.new_dependency.thresholds.typescript]
min_age_days = 60
min_downloads = 1000
```

Limites do que cada registro diz:

- **Uso (downloads):** só o npm (última semana) e o NuGet (total) contam. PyPI, Go e Maven não medem uso.
- **Idade no Go:** não é medida, porque a data que o proxy devolve é a do commit, escolhida pelo autor do módulo. Um pacote Go novo dá resultado **inconclusivo**, que a política (`on_inconclusive = premise`) registra como premissa no resumo, e só a existência é verificada.
- **Maven:** a busca devolve as versões da mais nova para a mais antiga; um artefato com mais de 1000 versões aparece mais novo do que é.
- **Rede:** sem acesso ao registro o resultado é inconclusivo.
- Mais de 50 dependências novas de uma vez dão resultado inconclusivo, em vez de 50 consultas.
- Este check só reprova ou informa. O registro de decisão (ADR) que uma dependência nova pede é do papel documentador.

Um manifesto que não pode ser lido (XML com declaração de tipo ou entidades, JSON ou TOML inválido, arquivo que não é texto) dá resultado inconclusivo, nunca “sem dependências”.

## Promover para bloqueio

Os checks começam em observação. Para bloquear, promova com uma decisão registrada no `forja.toml`:

```toml
[checks.sast]
mode = "blocking"
promotion = { date = 2026-11-01, reason = "regras revisadas em 30 PRs sem falso positivo" }
```

Vale o mesmo para `dependency_audit` e `new_dependency`. A política para “não consegui medir” é `block` no `sast` e no `dependency_audit` (ferramenta que falha bloqueia quando o gate bloqueia) e `premise` no `new_dependency`; pode ser trocada com `on_inconclusive = "block"` ou `"premise"` na mesma seção.

## Hoje

Nos papéis atuais (refatorar e corrigir) o agente só pode mudar código de produção, então o gate de escopo já rejeita qualquer mudança em manifesto. O `dependency_audit` e o `new_dependency` passam a valer quando um papel editar manifestos. O `sast` vale desde já.
