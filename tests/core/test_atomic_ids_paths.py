import os
import re
import sys
from pathlib import Path

import pytest

from forja.core.atomic import atomic_write_bytes
from forja.core.ids import new_id
from forja.core.paths import forja_home, run_dir


def test_atomic_write_creates_parents_and_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.bin"

    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two")

    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["file.bin"]


def test_antivirus_style_permission_errors_are_retried_with_doubling_delay(
    tmp_path: Path,
) -> None:
    target = tmp_path / "f"
    failures = [PermissionError(), PermissionError()]
    sleeps: list[float] = []

    def flaky_replace(src: Path, dst: Path) -> None:
        if failures:
            raise failures.pop()
        os.replace(src, dst)

    atomic_write_bytes(target, b"ok", replace=flaky_replace, sleep=sleeps.append)

    assert target.read_bytes() == b"ok"
    assert sleeps == [0.05, 0.1]


def test_permission_error_that_never_clears_gives_up_and_keeps_the_old_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "f"
    target.write_bytes(b"old")
    sleeps: list[float] = []

    def blocked(src: Path, dst: Path) -> None:
        raise PermissionError("locked")

    with pytest.raises(PermissionError):
        atomic_write_bytes(target, b"new", replace=blocked, sleep=sleeps.append, attempts=3)

    assert target.read_bytes() == b"old"
    assert len(sleeps) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["f"]


@pytest.mark.parametrize("stage", ["fsync", "replace"])
def test_a_crash_at_any_point_leaves_the_old_content_and_no_temp_file(
    tmp_path: Path, stage: str
) -> None:
    target = tmp_path / "f"
    target.write_bytes(b"old")

    def boom(*_: object) -> None:
        raise OSError("disk gone")

    kwargs = {"fsync": boom} if stage == "fsync" else {"replace": boom}
    with pytest.raises(OSError, match="disk gone"):
        atomic_write_bytes(target, b"new", **kwargs)  # type: ignore[arg-type]

    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["f"]


def test_ids_are_short_hex_and_unique() -> None:
    ids = {new_id() for _ in range(200)}

    assert len(ids) == 200
    assert all(re.fullmatch(r"[0-9a-f]{12}", i) for i in ids)


def test_forja_home_env_override_wins_everywhere() -> None:
    for platform in ("win32", "linux"):
        home = forja_home(environ={"FORJA_HOME": "/custom"}, platform=platform, home=Path("/h"))
        assert home == Path("/custom")


def test_forja_home_defaults_per_platform() -> None:
    windows = forja_home(
        environ={"LOCALAPPDATA": "C:/Users/me/AppData/Local"}, platform="win32", home=Path("/h")
    )
    assert windows == Path("C:/Users/me/AppData/Local/forja")

    windows_without_variable = forja_home(environ={}, platform="win32", home=Path("/h"))
    assert windows_without_variable == Path("/h/AppData/Local/forja")

    assert forja_home(environ={}, platform="linux", home=Path("/h")) == Path(
        "/h/.local/share/forja"
    )


def test_run_dir_lives_under_runs() -> None:
    result = run_dir("abc", environ={"FORJA_HOME": "/x"}, platform="linux", home=Path("/h"))

    assert result == Path("/x/runs/abc")


@pytest.mark.skipif(sys.platform == "win32", reason="a directory is flushed where it can be opened")
def test_the_directory_is_flushed_to_disk_on_posix(tmp_path: Path) -> None:
    from forja.core.atomic import _fsync_directory  # noqa: PLC0415

    flushed: list[int] = []

    _fsync_directory(tmp_path, flushed.append)

    assert len(flushed) == 1 and isinstance(flushed[0], int)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows cannot open a directory to flush it")
def test_on_windows_the_directory_is_not_flushed(tmp_path: Path) -> None:
    from forja.core.atomic import _fsync_directory  # noqa: PLC0415

    flushed: list[int] = []

    _fsync_directory(tmp_path, flushed.append)

    assert flushed == []
