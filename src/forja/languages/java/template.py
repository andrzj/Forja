"""The files of a new Java project: a Maven ``pom.xml``, a class and one JUnit test. Maven downloads
the plugins and JUnit itself when it first runs."""

from forja.core.adapters import GITATTRIBUTES, ProjectTemplate, project_words

GITIGNORE = """\
target/
"""


def template(name: str) -> ProjectTemplate:
    package = "com.example." + "".join(project_words(name))
    directory = package.replace(".", "/")
    return ProjectTemplate(
        {
            "pom.xml": f"""\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>{name}</artifactId>
  <version>0.1.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
""",
            f"src/main/java/{directory}/Version.java": f"""\
package {package};

/** The version of the project. */
public final class Version {{
    public static final String CURRENT = "0.1.0";

    private Version() {{
    }}
}}
""",
            f"src/test/java/{directory}/VersionTest.java": f"""\
package {package};

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class VersionTest {{
    @Test
    void theProjectHasAVersion() {{
        assertEquals("0.1.0", Version.CURRENT);
    }}
}}
""",
            ".gitignore": GITIGNORE,
            ".gitattributes": GITATTRIBUTES,
        }
    )
