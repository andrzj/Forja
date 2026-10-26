"""The files of a new Go project: ``go.mod``, a package and one test. Nothing is downloaded."""

from forja.core.adapters import GITATTRIBUTES, ProjectTemplate, project_words

GITIGNORE = """\
*.exe
*.test
*.out
"""


def template(name: str) -> ProjectTemplate:
    package = "".join(project_words(name))
    return ProjectTemplate(
        {
            "go.mod": f"module {name}\n\ngo 1.21\n",
            f"{package}.go": f"""\
// Package {package} is {name}.
package {package}

// Version is the version of the project.
const Version = "0.1.0"
""",
            f"{package}_test.go": f"""\
package {package}

import "testing"

func TestVersion(t *testing.T) {{
	if Version != "0.1.0" {{
		t.Fatalf("Version = %q, want 0.1.0", Version)
	}}
}}
""",
            ".gitignore": GITIGNORE,
            ".gitattributes": GITATTRIBUTES,
        }
    )
