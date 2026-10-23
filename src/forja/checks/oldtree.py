"""A private copy of the worktree turned back into the parent commit, for a check that must
measure what the attempt started from."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from forja.checks.changes import ChangeKind, Changes, write_files
from forja.checks.layout import skip_git_and_links


@contextmanager
def old_tree(
    worktree: Path, changes: Changes, texts: dict[str, str], prefix: str = "forja-before-"
) -> Iterator[Path]:
    """The worktree without ``.git`` and links, the files the attempt added or renamed removed
    and the parent commit's ``texts`` written in; gone when the block ends."""
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        root = Path(directory)
        shutil.copytree(
            worktree, root, symlinks=True, dirs_exist_ok=True, ignore=skip_git_and_links
        )
        for change in changes.files:
            if change.kind in (ChangeKind.ADDED, ChangeKind.RENAMED):
                (root / change.path).unlink(missing_ok=True)
        write_files(texts, root)
        yield root
