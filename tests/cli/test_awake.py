"""Staying awake: asked at the start, given up on every exit, never claimed where not done."""

import sys

import pytest

from forja.cli import awake


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    seen: list[int] = []

    def record(flags: int) -> int:
        seen.append(flags)
        return 1

    monkeypatch.setattr(awake, "_set_state", record)
    return seen


def test_it_asks_to_stay_awake_and_gives_it_up_after(
    monkeypatch: pytest.MonkeyPatch, calls: list[int]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    with awake.keep_awake() as asked:
        assert asked is True
        assert calls == [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED]
    assert calls[-1] == awake.ES_CONTINUOUS
    assert len(calls) == 2


def test_it_gives_it_up_when_the_run_fails(
    monkeypatch: pytest.MonkeyPatch, calls: list[int]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(RuntimeError), awake.keep_awake():
        raise RuntimeError("boom")
    assert calls[-1] == awake.ES_CONTINUOUS


def test_a_refusal_is_not_given_up_and_not_claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    monkeypatch.setattr(sys, "platform", "win32")

    def record(flags: int) -> int:
        seen.append(flags)
        return 0

    monkeypatch.setattr(awake, "_set_state", record)
    with awake.keep_awake() as asked:
        assert asked is False
    assert len(seen) == 1


def test_elsewhere_nothing_is_asked(monkeypatch: pytest.MonkeyPatch, calls: list[int]) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with awake.keep_awake() as asked:
        assert asked is False
    assert calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="the real call exists only on Windows")
def test_the_real_call_works_and_is_released() -> None:
    with awake.keep_awake() as asked:
        assert asked is True
