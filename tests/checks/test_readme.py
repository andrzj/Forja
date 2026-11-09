"""The README judged without a model: sections, commands, links, and what may change."""

import re

import pytest

from forja.checks.readme import (
    NO_README,
    Problem,
    chunks,
    cited_commands,
    evaluate,
    signature,
    touched_chunks,
)

FENCE = "`" * 3
GOOD = "\n".join(
    [
        "# Sample",
        "",
        "A library that adds numbers.",
        "",
        "## Build",
        "",
        FENCE + "bash",
        "go build ./...",
        FENCE,
        "",
        "## Tests",
        "",
        FENCE,
        "go test ./...",
        FENCE,
        "",
        "## Usage",
        "",
        "Call `Add`.",
        "",
        "## Configuration",
        "",
        "None.",
        "",
        "## Dependencies",
        "",
        "Go 1.22.",
        "",
    ]
)
BUILD = {("go", "build")}
TEST = {("go", "test")}


def problems(text: str | None, *, exists: bool = True) -> list[Problem]:
    return evaluate(text, lambda path: exists, BUILD, TEST)


def test_a_readme_that_answers_everything_is_approved() -> None:
    assert problems(GOOD) == []


def test_no_readme_is_one_problem_about_the_file() -> None:
    assert problems(None) == [Problem("readme", NO_README)]


def test_every_required_section_that_is_missing_is_named() -> None:
    found = problems(
        "# Sample\n\nWhat it is.\n\n## Build\n\n" + FENCE + "\ngo build\n" + FENCE + "\n"
    )
    assert [p.section for p in found] == ["test", "run", "configure", "dependencies"]
    assert all(p.heading is None for p in found)


def test_the_text_before_the_first_heading_says_what_it_is() -> None:
    found = problems("What it is.\n\n" + GOOD.split("\n\n", 2)[2])
    assert "what" not in {p.section for p in found}


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("Como construir", "build"),
        ("Instalação", "build"),
        ("Testar", "test"),
        ("Como executar", "run"),
        ("Configuração", "configure"),
        ("Dependências", "dependencies"),
        ("O que é", "what"),
    ],
)
def test_headings_in_portuguese_and_english_satisfy_the_sections(
    heading: str, section: str
) -> None:
    found = evaluate(f"# T\n\n## {heading}\n\ntext\n", lambda p: True)
    assert section not in {p.section for p in found}


def test_a_build_command_that_is_not_the_projects_is_found_and_names_the_section() -> None:
    text = GOOD.replace("go build ./...", "make build")
    found = problems(text)
    assert found == [
        Problem("build", "the build section cites make build; the project runs go build", "Build")
    ]


def test_a_section_with_no_command_at_all_is_found() -> None:
    text = GOOD.replace(FENCE + "bash\ngo build ./...\n" + FENCE, "Just build it.")
    assert [p.section for p in problems(text)] == ["build"]


def test_commands_are_compared_by_program_and_subcommand_through_launchers() -> None:
    assert signature(["python", "-m", "pytest", "-q"]) == ("pytest", "")
    assert signature(["uv", "run", "pytest", "tests"]) == ("pytest", "")
    assert signature(["/usr/bin/go", "build", "./..."]) == ("go", "build")
    assert signature(["./gradlew", "--no-daemon", "test"]) == ("gradle", "test")
    assert signature(["C:\\tools\\mvn.cmd", "-q", "test"]) == ("mvn", "test")
    assert signature([]) is None


def test_a_command_without_a_subcommand_matches_any_of_its_program() -> None:
    text = GOOD.replace("go test ./...", "go test")
    assert problems(text) == []
    assert evaluate(GOOD, lambda p: True, build={("go", "install")}) != []


def test_the_commands_of_a_section_are_the_lines_of_its_code_blocks_without_the_prompt() -> None:
    chunk = "\n".join(
        ["Run:", FENCE, "$ go build ./...", "# a comment", "", "PS C:\\x> go test", FENCE]
    )
    assert cited_commands(chunk) == [("go", "build"), ("go", "test")]


def test_a_command_in_running_text_is_not_a_command_the_reader_is_told_to_run() -> None:
    assert cited_commands("Use `make build` to build.") == []


def test_without_commands_from_the_adapter_the_section_is_not_compared() -> None:
    assert evaluate(GOOD.replace("go build ./...", "make build"), lambda p: True) == []


def test_a_link_to_a_file_that_is_not_there_is_found_with_its_section() -> None:
    text = GOOD.replace("Call `Add`.", "See [the guide](docs/guide.md) and [site](https://x.org).")
    found = problems(text, exists=False)
    assert found == [Problem("links", "the link to docs/guide.md points at nothing", "Usage")]
    assert problems(text) == []


def test_an_anchor_in_the_same_file_must_be_a_heading() -> None:
    text = GOOD.replace("Call `Add`.", "See [tests](#tests) and [none](#nowhere).")
    assert [p.message for p in problems(text)] == ["the link to #nowhere points at no heading"]


def test_a_link_inside_code_is_an_example_and_not_a_link() -> None:
    text = GOOD.replace(
        "Call `Add`.", "Write `[x](gone.md)` like this.\n\n" + FENCE + "\n[y](gone.md)\n" + FENCE
    )
    assert problems(text, exists=False) == []


def test_the_chunks_split_at_headings_outside_code_blocks() -> None:
    text = "intro\n\n# A\n\n" + FENCE + "\n# not a heading\n" + FENCE + "\n\n## B\n\nb\n"
    assert [c.heading for c in chunks(text)] == [None, "A", "B"]


def test_a_section_without_a_problem_must_come_back_as_it_was() -> None:
    old = GOOD.replace("go build ./...", "make build")
    found = problems(old)
    fixed = old.replace("make build", "go build ./...")
    assert touched_chunks(old, fixed, found) == []
    meddled = fixed.replace("None.", "Some.")
    assert touched_chunks(old, meddled, found) == ["Configuration"]


def test_new_sections_are_allowed_only_when_the_old_readme_lacked_a_required_one() -> None:
    old = GOOD.split("## Dependencies")[0]
    found = problems(old)
    assert [p.section for p in found] == ["dependencies"]
    assert touched_chunks(old, GOOD, found) == []
    complete = GOOD
    assert touched_chunks(complete, complete + "\n## Extra\n\nmore\n", problems(complete)) == [
        "Extra (new)"
    ]


def test_a_fence_opened_indented_and_closed_flush_ends_there() -> None:
    text = "# T\n  " + FENCE + "\ncode\n" + FENCE + "\n## Next\ntext"
    assert [c.heading for c in chunks(text)] == ["T", "Next"]


def test_cited_commands_stop_at_a_fence_opened_indented_and_closed_flush() -> None:
    chunk = "  " + FENCE + "\nmake build\n" + FENCE + "\nmake other\n"
    assert cited_commands(chunk) == [("make", "build")]


def test_a_link_after_a_fence_opened_indented_and_closed_flush_is_checked() -> None:
    text = "# T\n\nbody\n  " + FENCE + "\ncode\n" + FENCE + "\n[b](y.md)\n"
    found = evaluate(text, lambda path: False)
    assert [p.message for p in found if p.section == "links"] == [
        "the link to y.md points at nothing"
    ]


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["pytest"], ("pytest", "")),
        (["python", "-m"], ("python", "")),
        (["python", "script.py", "arg"], ("python", "")),
        (["node", "-m", "thing"], ("node", "")),
    ],
)
def test_only_python_dash_m_and_the_known_launchers_are_looked_through(
    tokens: list[str], expected: tuple[str, str]
) -> None:
    assert signature(tokens) == expected


@pytest.mark.parametrize(
    ("cited", "run", "matches"),
    [
        ("go", ("go", "build"), True),
        ("make build", ("make", ""), True),
        ("go build ./...", ("go", "build"), True),
        ("go test ./...", ("go", "build"), False),
        ("npm test", ("make", "test"), False),
    ],
)
def test_a_command_matches_by_program_and_by_subcommand_when_both_name_one(
    cited: str, run: tuple[str, str], matches: bool
) -> None:
    text = GOOD.replace("go build ./...", cited)
    found = evaluate(text, lambda path: True, {run}, TEST)
    assert ([p for p in found if p.section == "build"] == []) is matches


def test_an_empty_readme_lacks_every_section_and_a_lone_title_says_nothing() -> None:
    names = ["what", "build", "test", "run", "configure", "dependencies"]
    assert [p.section for p in evaluate("", lambda path: True)] == names
    assert "what" in [p.section for p in evaluate("# Sample\n", lambda path: True)]


def test_a_section_with_a_problem_does_not_let_a_new_section_in() -> None:
    old = "# T\n\ntext\n\n## Build\n\nmake\n"
    new = old + "\n## Extra\n\nmore\n"
    assert touched_chunks(old, new, [Problem("build", "m", "Build")]) == ["Extra (new)"]
    assert touched_chunks(old, new, [Problem("links", "m")]) == ["Extra (new)"]


def _model_readme(extra: tuple[str, ...] = ()) -> str:
    from forja.checks.readme import MODEL

    lines = ["# Sample", "", "Sample does one thing."]
    for name, _ in MODEL:
        lines += ["", f"## {name}", "", "text", *extra]
    return "\n".join(lines)


def test_every_section_of_the_model_that_answers_a_requirement_satisfies_it() -> None:
    from forja.checks.readme import MODEL, REQUIRED

    patterns = dict(REQUIRED)

    for name, answers in MODEL:
        if answers is not None:
            assert re.search(patterns[answers], name, re.IGNORECASE), name


def test_the_model_answers_every_requirement_of_the_gate() -> None:
    from forja.checks.readme import MODEL, REQUIRED

    answered = {answers for _, answers in MODEL}

    assert {name for name, _ in REQUIRED} <= answered


def test_a_readme_written_to_the_model_has_no_missing_section() -> None:
    problems = evaluate(_model_readme(), lambda path: True)

    assert [p for p in problems if p.section != "links"] == []
