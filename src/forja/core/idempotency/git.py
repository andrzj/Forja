import copy
import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from forja.core.process import Outcome, ProcessIdentity, ProcessRunner, ProcessSpec


class GitError(Exception):
    def __init__(self, args_: tuple[str, ...], exit_code: int | None, output: list[str]) -> None:
        self.exit_code = exit_code
        super().__init__(f"git {' '.join(args_)} failed ({exit_code}): {' | '.join(output[-3:])}")


@dataclass(frozen=True)
class GitResult:
    exit_code: int
    lines: list[str]


class _Collector:
    """Sink that keeps stdout lines for the caller and drops everything else."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def intent(self, operation_id: str, details: Mapping[str, object]) -> None:
        pass

    def started(self, operation_id: str, identity: ProcessIdentity) -> None:
        pass

    def progress(self, operation_id: str, channel: str, line: str) -> None:
        if channel == "out":
            self.lines.append(line)

    def effect(self, operation_id: str, details: Mapping[str, object]) -> None:
        pass


class Git:
    """Read-mostly git access for reconciliation, always through the process runner."""

    def __init__(
        self,
        repo: Path,
        *,
        executable: str,
        env: Mapping[str, str],
        timeout: float,
        log_dir: Path,
    ) -> None:
        self._repo = repo
        self._executable = executable
        self._env = env
        self._timeout = timeout
        self._log_dir = log_dir
        self._counter = itertools.count(1)

    @property
    def repo(self) -> Path:
        return self._repo

    def at(self, repo: Path) -> Self:
        """The same access (settings, log numbering) for another directory, such as a worktree."""
        clone = copy.copy(self)
        clone._repo = repo
        return clone

    async def run(self, *args: str) -> GitResult:
        """Run git and return its exit code and stdout lines; never raises on a non-zero exit."""
        number = next(self._counter)
        collector = _Collector()
        spec = ProcessSpec([self._executable, *args], self._repo, self._env, self._timeout)
        result = await ProcessRunner(collector).run(
            f"git-{number}", spec, self._log_dir / f"git-{number}.log"
        )
        if result.outcome is not Outcome.EXITED or result.exit_code is None:
            raise GitError(args, result.exit_code, [f"process {result.outcome.value}"])
        return GitResult(result.exit_code, collector.lines)

    async def lines(self, *args: str) -> list[str]:
        """Stdout lines of a command that must succeed."""
        result = await self.run(*args)
        if result.exit_code != 0:
            raise GitError(args, result.exit_code, result.lines)
        return result.lines

    async def succeeds(self, *args: str) -> bool:
        return (await self.run(*args)).exit_code == 0
