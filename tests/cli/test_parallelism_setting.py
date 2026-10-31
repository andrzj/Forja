"""``paralelismo`` in ``execucao.toml``: how many tasks of disjoint scope run at once."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from forja.cli.session import new_config
from forja.cli.settings import Execucao, dumps, load_execucao


def test_one_task_at_a_time_unless_the_file_says_otherwise() -> None:
    assert Execucao().paralelismo == 1


def test_the_number_is_kept_in_execucao_toml(tmp_path: Path) -> None:
    file = tmp_path / "execucao.toml"
    file.write_text(dumps(Execucao(paralelismo=3).model_dump()), encoding="utf-8")

    assert load_execucao(file).paralelismo == 3


def test_zero_tasks_at_once_is_refused() -> None:
    with pytest.raises(ValidationError):
        Execucao(paralelismo=0)


def test_the_run_configuration_carries_it(tmp_path: Path) -> None:
    config = new_config(
        repo=tmp_path,
        base_commit="a" * 40,
        executor_name="claude-code",
        executor_path=tmp_path / "claude",
        executor_version="1",
        tokens=10,
        parallel_tasks=3,
    )

    assert config.parallel_tasks == 3
