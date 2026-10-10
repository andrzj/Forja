"""Commands that must never reach the system, and input that travels by file."""

from pathlib import Path

import pytest

from forja.core.process import Outcome, ProcessSpec, UnsafeCommand, check_command_safety
from forja.core.process.model import MAX_ARGUMENT_CHARS
from tests.core.process.support import minimal_env, run_to_end, spec

SHELL_CHARACTERS = ["&", "|", "<", ">", "^", "%", '"', chr(10), chr(13)]


def test_a_command_needs_a_program() -> None:
    for command in ([], [""]):
        with pytest.raises(UnsafeCommand, match="no program"):
            check_command_safety(command)


def test_a_nul_character_is_refused_anywhere() -> None:
    with pytest.raises(UnsafeCommand, match="NUL"):
        check_command_safety(["tool", "a" + chr(0) + "b"])


def test_the_package_cannot_travel_as_an_argument() -> None:
    check_command_safety(["tool", "x" * MAX_ARGUMENT_CHARS])
    with pytest.raises(UnsafeCommand, match="file or stdin"):
        check_command_safety(["tool", "x" * (MAX_ARGUMENT_CHARS + 1)])


def test_a_command_line_that_is_too_long_in_total_is_refused() -> None:
    many = ["x" * 4000] * 8

    with pytest.raises(UnsafeCommand, match="too long"):
        check_command_safety(["tool", *many])


@pytest.mark.parametrize("program", ["agent.cmd", "agent.bat", "C:/tools/Agent.CMD", "run.Bat"])
@pytest.mark.parametrize("character", SHELL_CHARACTERS)
def test_batch_files_refuse_arguments_cmd_exe_could_misread(program: str, character: str) -> None:
    with pytest.raises(UnsafeCommand, match="cmd.exe"):
        check_command_safety([program, "--flag", "a" + character + "b"])


@pytest.mark.parametrize("program", ["agent.cmd", "agent.bat"])
def test_batch_files_accept_plain_arguments(program: str) -> None:
    check_command_safety([program, "--prompt-file", "C:/work/package.md", "--model=big-one", "-p"])


@pytest.mark.parametrize("character", SHELL_CHARACTERS)
def test_ordinary_programs_may_receive_any_text_because_no_shell_reads_it(character: str) -> None:
    check_command_safety(["python", "-c", "print('a" + character + "b')"])


def test_an_unsafe_command_cannot_even_be_described_as_a_process_spec(tmp_path: Path) -> None:
    with pytest.raises(UnsafeCommand):
        ProcessSpec(["agent.cmd", "a&b"], tmp_path, minimal_env(), timeout=5)


def test_stdin_file_is_fed_to_the_process(tmp_path: Path) -> None:
    package = tmp_path / "package.md"
    package.write_text("the whole package\nover two lines", encoding="utf-8")
    code = "import sys; print(sys.stdin.read().replace(chr(10), '|'))"
    process_spec = spec(code)
    process_spec = ProcessSpec(
        process_spec.command, tmp_path, process_spec.env, 20, stdin_file=package
    )

    result, sink = run_to_end(process_spec, tmp_path / "op.log")

    assert result.outcome is Outcome.EXITED
    assert sink.lines("out") == ["the whole package|over two lines"]
    assert sink.of("intent")["stdin_file"] == str(package)  # type: ignore[index]


def test_without_stdin_file_the_process_sees_an_empty_input(tmp_path: Path) -> None:
    _, sink = run_to_end(spec("import sys; print(repr(sys.stdin.read()))"), tmp_path / "op.log")

    assert sink.lines("out") == ["''"]


def test_a_missing_stdin_file_is_a_failure_to_start_not_a_crash(tmp_path: Path) -> None:
    base = spec("pass")
    broken = ProcessSpec(base.command, tmp_path, base.env, 20, stdin_file=tmp_path / "nope.md")

    result, sink = run_to_end(broken, tmp_path / "op.log")

    assert result.outcome is Outcome.SPAWN_FAILED
    assert sink.kinds() == ["intent", "effect"]
