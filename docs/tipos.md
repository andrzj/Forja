# Tipos do Python: o check de análise estática

A Forja reprova a tentativa que introduz erro de tipo novo em arquivo Python. Quem mede é o `mypy` (ADR 0039). O check é o `types`, do gate 3, e nasce em modo observação: reporta e não reprova até o repositório promovê-lo. Só o Python precisa dele: TypeScript, Java, Go e C# já têm análise de tipos no compilador ou nas ferramentas do lint.

## O que mede

- **Só erro novo.** É a mesma catraca do `lint`: a Forja conta os erros por (arquivo, código do `mypy`) na base e na tentativa, e reprova o que aumentou. Número de linha, coluna e texto da mensagem não entram na chave, porque mudam com qualquer edição ou versão da ferramenta.
- **Só arquivos que a tentativa mudou.** Erro antigo, ou em arquivo que ela não tocou, não reprova.
- **Só `severity` igual a `error`.** Notas do `mypy` não contam.
- **Só o arquivo pedido.** O `mypy` roda com `--follow-imports=silent`: usa os tipos dos módulos importados e esconde os erros deles.
- **Import não achado não conta.** `import-not-found` e `import-untyped` ficam desligados: o ambiente do repositório pode não ter tudo, e isso não é defeito da tentativa.
- **Modo padrão do `mypy`, não o estrito.** Código sem anotação quase não é verificado.

## Como roda

```text
<mypy> --python-executable <python do repositório> --config-file= --follow-imports=silent
       --output json --cache-dir <dispositivo nulo> --disable-error-code=import-not-found
       --disable-error-code=import-untyped -- <arquivos mudados>
```

- O `--python-executable` é o interpretador do repositório (o mesmo que roda os testes), então as dependências instaladas nele resolvem.
- **A configuração do repositório não vale** (`--config-file=`): um `plugins` em `mypy.ini` ou `pyproject.toml` é execução de código que o agente escreveu, e a base e a tentativa precisam das mesmas opções.
- **Sem cache:** a base e a tentativa não se contaminam e nada cai na worktree. Cada execução refaz a análise.

## Ajustar

Para dar ao `mypy` outras opções, use o `forja.toml`, que é política congelada da execução e não texto da tentativa. O comando declarado substitui o da Forja inteiro, então precisa trazer `--output json` e o resto de que a leitura depende:

```toml
[checks.types.commands]
types = ["python", "-m", "mypy", "--strict", "--output", "json", "--cache-dir", "/dev/null", "--"]
```

Para promover o gate a bloqueante, use `mode = "blocking"` em `[checks.types]`, com `promotion = { date, reason }` e `on_inconclusive`, como nos outros checks (`docs\plano-endurecimento.md`).

## Quando fica sem resposta

Falha da ferramenta nunca aprova: o resultado é `Inconclusive`. Isso vale para o `mypy` ausente, para saída diferente de 0 e 1, para JSON ilegível e para saída 1 sem nenhum erro lido. O `forja doctor` avisa quando o `mypy` falta, sem tornar isso obrigatório.

## Instalar o `mypy`

`forja instalar` o instala na pasta da Forja, quando detecta Python no repositório (ver `docs\instalacao.md`). A roda é a pura (`py3-none-any`), mais lenta que as compiladas, mas serve a qualquer Python. As dependências dela (`pip`) não têm checksum no manifesto.

## Limites

- **A tentativa pode esconder erro.** `# type: ignore` e o comentário `# mypy:` no código dela calam o `mypy`, que não tem opção para ignorá-los (o `ruff` tem `--ignore-noqa`). Só a revisão do ramo pega isso.
- **Erro novo pode vir de outro arquivo.** Mudar a assinatura de uma função quebra quem a chama; a catraca é por arquivo mudado, como a do lint.
- **Em aberto para o E2E:** o `--python-executable` com o ambiente virtual da execução (`<run>\venv`) e com instalação editável; o JSON em execução limpa; o código de saída no Windows.
- Na barra de gates da UI o `types` entra no gate 3 (lint), com `format` e `lint`.

O plano está em `docs\plano-analise-estatica.md`.
