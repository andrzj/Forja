# Plano: documentação do usuário

Ordem expressa do dono (08/11/2026), fora da fila 18. Referência do dono: o modelo de README do gist `KAYOKG/176fc612c1f8cc476c1c4ff558453dec` (lido por inteiro em 08/11/2026): título, selos, status, índice de tópicos com links, descrição, funcionalidades, pré-requisitos, como rodar, como rodar os testes, casos de uso, configuração, tecnologias, problemas, tarefas em aberto, contribuintes, licença.

## O que o dono pediu

1. O README da Forja segue o modelo do gist. **Feito em 08/11/2026** (`README.md` reescrito, ainda sem a documentação rica dos passos abaixo).
2. O documentador da Forja aplica o mesmo modelo ao README que cria nos projetos em que a Forja trabalha.
3. A documentação do usuário, a partir do README, é muito rica e extensa, com arquivos de markdown específicos e **exemplos** em todos os casos.
4. Todas as possibilidades de uso, todo argumento, toda configuração e todo arquivo de configuração que o usuário pode dar à Forja estão documentados, cada um com exemplo comentado e explicado.
5. Os markdown soltos de `docs\` são lidos por inteiro, os que podem ser unidos são unidos e os redundantes são eliminados.
6. O Plano de execução e os documentos sobre o desenvolvimento da Forja ficam fora do README e dos filhos dele.

## Decisões deste plano

- **Pasta nova `docs\guia\`** guarda toda a documentação do usuário. O que é do desenvolvimento da Forja fica onde está e não é citado no README nem no guia: `Plano de execução.md`, `Especificação.md`, `registro-arquivo.md`, `estado.md`, `plano-*.md`, `aceitacao-3a.md`, `aceitacao-3b.md`, `defeitos-3.md`, `medicao-2.md`, `medicao-2-relatorio.md`, `adr\`.
- **Os ADRs não são do guia.** O README e o guia não os citam. Os ADRs e planos que apontam para um arquivo unido ou movido passam a apontar para o novo caminho (histórico preservado, só o caminho muda).
- **Estrutura do guia (cada arquivo com exemplos comentados):**
  - `docs\guia\README.md`: índice do guia.
  - `instalacao.md`: instalar, `forja doctor`, `forja instalar`, atualizar, remover (de `instalacao.md`).
  - `comandos.md`: todos os comandos e argumentos da linha de comando, cada um com exemplo (de `cli\args.py`; absorve `especificar-e-investigar.md`).
  - `execucao-toml.md`: cada chave do `execucao.toml`, o modo CI, o arquivo de confiança, a prevenção de suspensão (de `modo-ci.md` e de `cli\settings.py`).
  - `forja-toml.md`: cada chave de política (modo, limiares, comandos), por gate (de `limiares.md` e de `core\policy\config.py`).
  - `clis.md`: CLI por papel, executável de cada CLI, autor de testes diferente, adaptador genérico `[clis.<nome>]` (de `clis-por-papel-e-adaptador-generico.md`).
  - `gates\`: um arquivo por assunto, sem perder conteúdo: `seguranca-e-dependencias.md`, `arquitetura-e-dependencias.md`, `teste-diferencial.md`, `e2e-e-dados-de-teste.md`, `duplicacao.md`, `tipos.md`, `teste-de-propriedades.md`, `mutacao.md` (absorve `mutacao-incremental.md`), com um `gates\README.md` que lista os 14 gates e o modo de cada um.
  - `documentacao-gerada.md`: o que o documentador escreve, o modelo do README gerado, a voz (absorve `voz.md`).
  - `diario-de-bordo.md`, `paralelismo.md`: movidos sem unir (assuntos distintos).
  - `ambiente.md`: variáveis de ambiente que a Forja lê, pastas e arquivos que ela cria (`FORJA_HOME`, `.forja-agent`, `forja-run/<id>`, `resumo.md` e os demais).
- **Eliminados ao unir:** `modo-ci.md`, `limiares.md`, `especificar-e-investigar.md`, `mutacao-incremental.md`, `voz.md`, `clis-por-papel-e-adaptador-generico.md` e os caminhos antigos dos demais. Nada é apagado antes de o conteúdo estar no arquivo novo.
- **Regra de conteúdo:** onde o texto atual está certo, é mantido; o que falta é acrescentado a partir do código (nunca de memória); o que está errado é corrigido e dito no Registro. Todo exemplo de comando e de TOML é conferido contra o código ou rodado.
- **Voz do guia:** a do documentador da Forja (`docs\guia\documentacao-gerada.md`): sem travessão, cumprimento, oferta, elogio ou emoji.

## Passos (um commit por passo; o Registro é atualizado no mesmo commit)

0. Este plano, a Fila e o Registro. **Feito (08/11/2026).**
1. **Inventário a partir do código**, sem escrever documentação: lista de todos os comandos e argumentos (`cli\args.py`), todas as chaves do `execucao.toml` (`cli\settings.py`), todas as chaves do `forja.toml` (`core\policy\config.py` e os checks), os campos do `[clis.<nome>]`, o arquivo de fatos, as regras do Semgrep, os arquivos de camadas e do diferencial, as variáveis de ambiente e os arquivos que a Forja cria. Resultado: `docs\guia\inventario.md` temporário, apagado no passo 8.
2. **Leitura por inteiro** dos markdown de usuário atuais (instalacao, modo-ci, limiares, especificar-e-investigar, clis-por-papel-e-adaptador-generico, seguranca-e-dependencias, arquitetura-e-dependencias, teste-diferencial, e2e-e-dados-de-teste, duplicacao, tipos, teste-de-propriedades, mutacao-incremental, documentacao-gerada, voz, diario-de-bordo, paralelismo) e mapa do que vai para onde, no Registro.
3. `comandos.md` e `ambiente.md`.
4. `execucao-toml.md`, `forja-toml.md` e `clis.md`.
5. `gates\` (um arquivo por assunto e o índice).
6. `documentacao-gerada.md`, `diario-de-bordo.md`, `paralelismo.md`, `instalacao.md` e o índice `docs\guia\README.md`.
6A. **Capturas de tela** (ordem do dono, 08/11/2026): imagens em `docs\guia\imagens\`, cada uma citada no arquivo do guia do assunto, com uma linha dizendo o cenário e o comando. (a) TUI em cenários controlados: o app do Textual rodado com o piloto de teste e a tela salva em SVG por `export_screenshot` (execução em andamento, `d` detalhes, `l` log, rejeição de gate, entrega, bloqueio, interrompida por `q`, barra dos gates 1 a 12, temas); (b) comandos e execução real: a Forja dentro de um pseudoterminal do Windows (ConPTY, `pywinpty`) de largura que mostre os 12 gates, tela lida por emulador (`pyte`) e renderizada em PNG (`forja --help`, `forja doctor`, `forja instalar`, `--plano`, modo texto de CI, `resumo.md`, uma execução real com o `claude-code`). O script que gera as capturas fica em `scripts\capturas\` para regenerar quando a interface mudar; as dependências do script (`pywinpty`, `pyte`, biblioteca de imagem) ficam num grupo de dependência próprio, fora das de execução do pacote. Limite: é a tela do terminal renderizada, não a janela do Windows Terminal.
7. **README da Forja** reescrito como porta de entrada rica: cada seção do modelo do gist com o resumo e o link para o arquivo do guia que a detalha, sem citar o Plano nem documentos de desenvolvimento.
8. **Limpeza:** apagar os arquivos unidos e movidos, apagar o `inventario.md`, corrigir os caminhos em ADRs, planos, mensagens de erro do código (`core\policy\config.py` cita `docs/voz.md`) e testes; `grep` por caminho antigo não acha nada.
9. **Teste de cobertura da documentação:** um teste que falha quando um argumento de `cli\args.py` ou uma chave do `execucao.toml` ou do `forja.toml` não aparece em `docs\guia\`.
10. **Regra do documentador:** o modelo do gist entra em `DOCUMENTER_INSTRUCTIONS` (`orchestrator\agent_runner.py`) e em `checks\readme.py` (as seções do modelo que o gate exige continuam compatíveis com `REQUIRED`); testes; gate de mutação nos arquivos alterados; E2E curto com o `claude-code` real num repositório descartável. Depois dos passos 3 a 9 para o README gerado poder apontar para o guia como exemplo.

## Limites declarados

- O gist usa selos e emoji (`:heavy_check_mark:`). O guia e o README gerado usam selos e não usam emoji, porque a regra de voz do dono (item 10 da Fila) proíbe emoji em documentação. O dono decide se quer outra coisa.
- O README não terá capturas de tela nem deploy: a Forja é uma ferramenta de terminal e não há deploy.
