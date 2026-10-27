"""The inputs of the differential cases are copied out of the worktree, from the base."""

from pathlib import Path

import pytest

from forja.checks.differential_inputs import MissingInput, freeze_inputs
from forja.core.policy import DifferentialCase


def case(name: str, stdin: str = "") -> DifferentialCase:
    return DifferentialCase(name, ("app",), stdin=stdin)


def test_the_input_is_copied_outside_the_worktree_and_a_later_edit_does_not_reach_the_copy(
    tmp_path: Path,
) -> None:
    worktree, kept = tmp_path / "work", tmp_path / "kept"
    (worktree / "inputs").mkdir(parents=True)
    (worktree / "inputs" / "a.json").write_bytes(b'{"seed": 7}\r\n')

    frozen = freeze_inputs([case("report", "inputs/a.json")], worktree, kept)
    (worktree / "inputs" / "a.json").write_bytes(b"{}")

    assert frozen == {"report": kept / "report.stdin"}
    assert frozen["report"].read_bytes() == b'{"seed": 7}\r\n'
    assert worktree not in frozen["report"].parents


def test_a_case_without_input_has_no_copy_and_makes_no_directory(tmp_path: Path) -> None:
    frozen = freeze_inputs([case("report")], tmp_path, tmp_path / "kept")

    assert frozen == {}
    assert not (tmp_path / "kept").exists()


@pytest.mark.parametrize("stdin", ["missing.json", "dir", "../outside.json", "/abs.json"])
def test_an_input_that_is_not_a_file_inside_the_worktree_is_refused(
    tmp_path: Path, stdin: str
) -> None:
    worktree = tmp_path / "work"
    (worktree / "dir").mkdir(parents=True)
    (tmp_path / "outside.json").write_text("x")

    with pytest.raises(MissingInput) as info:
        freeze_inputs([case("report", stdin)], worktree, tmp_path / "kept")

    assert info.value.case == "report" and info.value.path == stdin
    assert "report" in str(info.value) and stdin in str(info.value)


def test_an_input_reached_through_a_link_is_refused(tmp_path: Path) -> None:
    worktree = tmp_path / "work"
    worktree.mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    try:
        (worktree / "link.txt").symlink_to(tmp_path / "secret.txt")
    except OSError:
        pytest.skip("the system does not let this user create links")

    with pytest.raises(MissingInput):
        freeze_inputs([case("report", "link.txt")], worktree, tmp_path / "kept")
