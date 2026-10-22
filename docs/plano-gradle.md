# Plano: Gradle no adaptador Java

A Especificação diz "Maven ou Gradle". Hoje `languages\java\adapter.py` só fala Maven. Este plano vem da leitura do adaptador Maven e de execuções reais do Gradle 9.8.2 (JDK 21), instalado em `C:\Users\jbrav\tools\gradle-9.8.2` (sem admin; o `choco` falhou). Projetos de exemplo: scratchpad `gsample` e `g2`.

## O que a execução real mostrou

| Tema | Fato observado |
|---|---|
| Versão | `gradle -v` imprime `Gradle 9.8.2` |
| Saída | `--console plain`; `NO_COLOR` não é necessário |
| Build | `gradle compileJava compileTestJava`; erro: `<caminho>:<linha>: error: <msg>` (formato `javac`, não o `[ERROR] x.java:[l,c]` do Maven); saída 1 |
| Testes | `gradle cleanTest test`; saída 1 se algum teste falha; XML em `build/test-results/test/TEST-*.xml`, mesmo formato JUnit/Surefire (`testcase classname name`; JUnit 5 acrescenta `()` ao nome: `adds()`); sem testes: o diretório não existe |
| Cobertura | O plugin `jacoco` precisa estar aplicado. Init script aplica o plugin a todo projeto `java` e liga o XML: `build/reports/jacoco/test/jacocoTestReport.xml` (formato igual ao do Maven). `jacocoTestReport` não roda se `test` falha: usar `--continue` |
| Checkstyle | `checkstyleMain`; XML `build/reports/checkstyle/main.xml` (`<file name=<abs>><error line severity message source>`), ligado por padrão; severidade `error` falha o build, por isso `ignoreFailures = true` por init script |
| PMD | `pmdMain`; XML `build/reports/pmd/main.xml`, mesmo esquema de namespace do Maven |
| SpotBugs | `spotbugsMain`; XML só com init script (`reports { xml { required = true } }` nas tarefas `spotbugs*`): `build/reports/spotbugs/main.xml`; `sourcepath` como no Maven (`com/acme/Bad.java`) |
| Spotless | `spotlessCheck`; falha lista `src\main\java\...\X.java` (barra invertida, indentação de 6) sob "The following files had format violations"; `-PspotlessIdeHook=<caminho absoluto>` restringe a um arquivo e imprime `IS DIRTY` se sujo, sem falhar a tarefa |
| Referência de classe em init script | `com.github...SpotBugsTask` não resolve no init script: casar tarefas por nome |

## Decisões

1. **Detecção:** `build.gradle` ou `build.gradle.kts` (raiz). Se há `pom.xml` e Gradle, vale o Maven (já existente); decisão do dono para empate: não há, escolho Maven por ser o que já existe.
2. **Executável:** `gradlew`/`gradlew.bat` do repositório se existir (a worktree o contém), senão `gradle` no PATH. Nada é instalado ou baixado pelo adaptador além do que o projeto declara.
3. **Plugins:** nada é aplicado ao projeto, exceto o JaCoCo (nomeado em init script, como o Maven nomeia o goal). Lint e formato só rodam se o `build.gradle[.kts]` os declara (`checkstyle`, `pmd`, `com.github.spotbugs`, `com.diffplug.spotless`); senão `NotSupported`, como no Maven.
4. **Init scripts:** o adaptador não grava nada na worktree; só descreve comandos. Os scripts entram como argumentos `-I` apontando para arquivos que o adaptador mantém em `languages\java\init_scripts\` (`coverage`, `lint`, `spotbugs`; pacote de dados), lidos pelo caminho do módulo.
5. **Formato:** a checagem roda sempre no projeto inteiro (`spotlessCheck`; o parser lista todos os arquivos sujos e o "antes" da Forja separa o que já estava sujo). `-PspotlessIdeHook=<caminho>` só imprime `IS DIRTY` sem o nome do arquivo, por isso só vale em `spotlessApply`, para um arquivo.
6. **Sem filtro de testes** (igual ao Maven): `NotSupported` se há `tests`/`test_files`.
7. **Arquivos ignorados** no `classify`: `build` e `.gradle` já estão em `_SKIPPED_DIRECTORIES`.
8. **`config_files`:** `build.gradle`, `build.gradle.kts`, `settings.gradle[.kts]`, `gradle.properties`, `gradle/libs.versions.toml`, `gradle/wrapper/gradle-wrapper.properties`, `config/checkstyle/checkstyle.xml`, `config/pmd/ruleSet.xml`.

## Passos (um commit cada)

1. `languages\java\gradle.py`: planos de comando (build, test, coverage, lint, format) e init scripts; `adapter.py` escolhe Maven ou Gradle por manifesto no `plan`/`detect`/`tool_info`. Testes de unidade dos planos.
2. `languages\java\parsers.py`: parâmetro de ferramenta onde o formato muda: erro de compilação do `javac`, lista do Spotless, Checkstyle por XML, caminhos dos relatórios. Testes com texto copiado das execuções acima.
3. `cli\detect.py`, `cli\prepare.py` (mensagem), `cli\doctor.py` (Gradle no PATH ou `gradlew`).
4. Ponta a ponta real com Gradle em `tests\checks\test_real_languages.py` (marker `slow`), no molde do Maven.
5. Gate de mutação nos arquivos novos; atualizar `NOTAS.md` e a documentação.

## Limites já conhecidos

- Sem `gradlew` e sem Gradle no PATH: `detect` não confirma a ferramenta (versão ausente).
- O Gradle baixa plugins e dependências na primeira vez (rede); `--offline` não é usado.
- Projetos com vários módulos: relatórios em `*/build/...`; o primeiro passo cobre a raiz e o padrão `**/build/...` onde o Maven já usa `**/target/...`.
- Daemon: `--no-daemon` não é passado. Medido no passo 4 (Windows): ao fim do ponta a ponta nenhum processo `java` sobrou e `gradle --status` mostrou todos os daemons STOPPED.
- JUnit 5: o Gradle grava o método sem parâmetros como `adds()`; o parser tira o `()` final para o id bater com o do Maven.

## Estado

Passos 1 a 5 feitos. Ponta a ponta real em `tests\checks\test_real_languages.py` (projeto `GRADLE`).
