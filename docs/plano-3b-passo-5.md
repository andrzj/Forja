# Plano do passo 5 do 3b: executor de mutantes agnóstico

Contexto: ADR 0020 mantém o motor próprio de mutação de Python. O executor roda mutantes de qualquer
linguagem; só o comando de teste e o mapa linha→testes vêm do adaptador.

## Medição (Windows nativo, repositório da Forja)

Copiar a árvore (443 arquivos, sem `.git`, `.venv` e caches) leva ~0,7 s; apagar leva ~1,4 s. O custo
é por worker, não por mutante.

## Contrato

Módulo novo `src/forja/mutation/executor.py`, sem importar nada específico de Python.

- Entrada: mutantes (arquivo, `Site`, testes que cobrem a linha), comando de teste do adaptador com o
  teste mapeado como argumento, timeout, número de workers.
- Saída: `MutationReport` de `core/reports/models.py`, com um `MutantResult` por mutante. O modelo
  ainda não foi relido para este plano; confirmar os campos antes de codar.
- Processos: reaproveitar o caminho que `checks/build_and_tests.py` usa (Job Object, ambiente
  filtrado), não um `subprocess` novo. Ler esse arquivo antes de codar.

## Algoritmo

1. Cada worker faz uma cópia descartável do worktree, ignorando `.git`, `.venv` e caches.
2. Canário: roda os testes mapeados na cópia limpa. Se falhar, devolve `Inconclusive` sem mutar.
3. Por mutante: escreve o arquivo mutado (`apply_site`), roda só os testes que cobrem a linha com
   timeout e restaura o original em `finally`. Testes falham = `KILLED`; passam = `SURVIVED`;
   estouro de tempo = `TIMEOUT`; nenhum teste cobre = `NO_COVERAGE` (conta contra a nota).
4. Paralelismo: `asyncio` com semáforo; cada worker é dono de uma cópia e processa um mutante por vez.
   Padrão `min(4, núcleos)`, configurável pela política TOML.
5. Timeout por mutante: 3× o tempo do canário, piso de 10 s.
6. Risco do `.pyc` velho: arquivo mutado com mesmo tamanho e mtime pode reaproveitar o `.pyc` e testar
   o código original. Mitigação: `PYTHONDONTWRITEBYTECODE=1` e apagar `__pycache__` da cópia. Teste
   que prove a mitigação.

## Testes (`tests/mutation/test_executor.py`)

Projeto mínimo em `tmp_path` com: mutante que morre, que sobrevive, que dá timeout (`while True`), sem
cobertura, canário que falha. Também cobre a restauração do arquivo e o caso do `.pyc`.

## Fora do escopo

`MutationCheck` e registro do gate (passo 6); mapeamento linha→testes a partir do relatório de
cobertura já lido.
