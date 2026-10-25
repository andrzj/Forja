"""What a document cites between backticks, and what the repository still has of it."""

import pytest

from forja.checks.doc_drift import (
    COMMAND,
    PATH,
    SYMBOL,
    Facts,
    Reference,
    candidates,
    drift,
    make_targets,
    package_scripts,
    references,
)

FENCE = "`" * 3
FACTS = Facts(
    files=frozenset({"src/app/core.py", "docs/guide.md", "Makefile", "package.json"}),
    words=frozenset({"build_all", "Runner", "run", "core", "app", "os", "path"}),
    make_targets=frozenset({"build", "test"}),
    scripts=frozenset({"lint"}),
)


def kinds(text: str) -> list[tuple[str, str]]:
    return [(r.kind, r.token) for r in references("README.md", text)]


def gone(text: str, document: str = "README.md") -> list[str]:
    return [r.span for r, _ in drift({document: text}, FACTS)]


def test_only_what_is_between_backticks_is_read_and_a_fenced_block_is_not() -> None:
    text = f"see src/app/gone.py and `build_all()`\n{FENCE}\n`src/app/gone.py`\n{FENCE}\n"
    assert kinds(text) == [(SYMBOL, "build_all")]


@pytest.mark.parametrize(
    ("span", "kind", "token"),
    [
        ("src/app/core.py", PATH, "src/app/core.py"),
        ("src/app/core.py:12-30", PATH, "src/app/core.py"),
        ("forja.toml", PATH, "forja.toml"),
        ("docs/", PATH, "docs/"),
        ("make build", COMMAND, "make build"),
        ("make -j4 test", COMMAND, "make test"),
        ("npm run lint -- --fix", COMMAND, "npm run lint"),
        ("run()", SYMBOL, "run"),
        ("Runner.run", SYMBOL, "Runner.run"),
        ("build_all", SYMBOL, "build_all"),
        ("buildAll", SYMBOL, "buildAll"),
    ],
)
def test_a_span_is_a_path_a_command_or_a_symbol(span: str, kind: str, token: str) -> None:
    assert kinds(f"`{span}`") == [(kind, token)]


@pytest.mark.parametrize(
    "span",
    [
        "run",
        "README",
        "--flag",
        "https://x.dev/a.md",
        "~/x.py",
        "/etc/x",
        "a b",
        "src/*.py",
        "x=1",
        "pip install",
    ],
)
def test_words_flags_urls_and_globs_are_not_citations(span: str) -> None:
    assert kinds(f"`{span}`") == []


def test_a_path_is_found_from_the_root_or_from_the_folder_of_the_document() -> None:
    assert gone("`src/app/core.py` `core.py`", "docs/guide.md") == ["core.py"]
    assert gone("`guide.md`", "docs/other.md") == []
    assert gone("`src/app`") == []
    assert gone("`src/app/none.py`") == ["src/app/none.py"]


def test_a_path_that_leaves_the_repository_is_not_judged() -> None:
    assert gone("`../outside.py`") == []


def test_a_make_target_or_an_npm_script_must_be_declared() -> None:
    assert gone("`make build` `make deploy` `npm run lint` `npm run gone`") == [
        "make deploy",
        "npm run gone",
    ]


def test_a_symbol_is_there_while_some_file_has_the_word_and_every_part_of_it_counts() -> None:
    assert gone("`build_all()` `Runner.run` `os.path`") == []
    assert gone("`build_everything()` `Runner.stop`") == ["build_everything()", "Runner.stop"]


def test_the_finding_names_what_is_gone() -> None:
    ((reference, missing),) = drift({"README.md": "x `Runner.stop`"}, FACTS)
    assert (reference.line, missing) == (1, ["stop"])


def test_targets_of_a_makefile_and_scripts_of_a_package() -> None:
    assert make_targets(".PHONY: all\nall build: dep\n\tcc\nX := 1\n\ttest:\ntest:\n") == {
        "all",
        "build",
        "test",
    }
    assert package_scripts('{"scripts": {"a": "x", "b": "y"}}') == {"a", "b"}
    assert package_scripts("not json") == set()
    assert package_scripts('{"scripts": 3}') == set()


def test_a_fence_opened_indented_and_closed_flush_ends_there() -> None:
    text = "  " + FENCE + "\n`src/a.py`\n" + FENCE + "\n`gone/z.py`\n"
    assert kinds(text) == [(PATH, "gone/z.py")]


@pytest.mark.parametrize("span", ["npm install left-pad", "npm run", "foo run build"])
def test_what_is_not_a_launcher_running_a_script_is_not_a_command(span: str) -> None:
    assert kinds(f"`{span}`") == []


def test_a_path_is_looked_for_only_where_it_stays_inside_the_repository() -> None:
    def cited(path: str, document: str = "README.md") -> list[str]:
        return candidates(Reference(document, 1, PATH, path, path))

    assert cited("../x.py") == []
    assert cited("/abs/x.py") == []
    assert cited(".") == []
    assert cited("../x.py", "docs/g.md") == ["x.py"]
