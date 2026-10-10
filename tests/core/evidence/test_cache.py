from pathlib import Path

import pytest

from forja.core.evidence import (
    EvidenceCache,
    EvidenceNotAllowed,
    EvidenceStore,
    ToolRunStore,
    cache_key,
)
from forja.core.idempotency import Decision, reconcile_run_tool
from tests.core.evidence.test_models import CONTEXT, evidence
from tests.core.evidence.test_stores import record_run


def key(**changes: object) -> str:
    return cache_key(evidence(context={**CONTEXT, **changes}).context)


def test_the_key_is_a_sha256_and_equal_contexts_give_equal_keys() -> None:
    assert len(key()) == 64 and key() == key()


@pytest.mark.parametrize(
    ("field", "other"),
    [
        ("commit", "e" * 40),
        ("tool", "radon"),
        ("tool_version", "1.18.0"),
        ("config_hash", "cfg-other"),
        ("toolchain", "node"),
        ("toolchain_version", "3.13.0"),
        ("platform", "linux-x86_64"),
        ("scope", ["src/a.py"]),
    ],
)
def test_every_part_of_the_context_changes_the_key(field: str, other: object) -> None:
    assert key(**{field: other}) != key()


def test_the_policy_version_is_not_part_of_the_key() -> None:
    assert key(policy_version="2027.01") == key()


def test_the_order_of_the_scope_is_not_part_of_the_key() -> None:
    assert key(scope=["src/a.py", "src/b.py"]) == key(scope=["src/b.py", "src/a.py"])


def test_values_that_would_merge_if_joined_stay_distinct() -> None:
    assert key(tool="ab", tool_version="c") != key(tool="a", tool_version="bc")
    assert key(scope=["ab"]) != key(scope=["a", "b"])


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ToolRunStore, EvidenceStore]:
    runs = ToolRunStore(tmp_path / "run")
    record_run(runs, tmp_path)
    return runs, EvidenceStore(tmp_path / "run", runs)


def test_a_measurement_is_found_again_only_under_its_whole_key(
    stores: tuple[ToolRunStore, EvidenceStore],
) -> None:
    cache = EvidenceCache(stores[1])
    cache.put(evidence())

    assert cache.has(key())
    assert [e.id for e in cache.find(key())] == ["ev1"]
    for different in (key(commit="e" * 40), key(config_hash="x"), key(scope=["other.py"])):
        assert not cache.has(different)
        assert cache.find(different) == ()


def test_evidence_from_one_tool_run_shares_a_key_and_comes_back_ordered(
    stores: tuple[ToolRunStore, EvidenceStore],
) -> None:
    cache = EvidenceCache(stores[1])
    cache.put(evidence(id="ev-b", measurement="nloc"))
    cache.put(evidence(id="ev-a", measurement="complexity"))

    assert [e.id for e in cache.find(key())] == ["ev-a", "ev-b"]


def test_reopening_rebuilds_the_index_from_the_stored_evidence(
    stores: tuple[ToolRunStore, EvidenceStore],
) -> None:
    EvidenceCache(stores[1]).put(evidence())

    reopened = EvidenceCache(stores[1])

    assert reopened.has(key())
    assert reopened.damaged == []


def test_damaged_evidence_is_left_out_and_listed_without_blocking_the_rest(
    stores: tuple[ToolRunStore, EvidenceStore], tmp_path: Path
) -> None:
    store = stores[1]
    cache = EvidenceCache(store)
    cache.put(evidence(id="ev-good"))
    cache.put(evidence(id="ev-bad", context={**CONTEXT, "tool": "radon"}))
    (tmp_path / "run" / "evidence" / "ev-bad.json").write_bytes(b"garbage")

    reopened = EvidenceCache(store)

    assert reopened.has(key())
    assert not reopened.has(key(tool="radon"))
    assert [i for i, _ in reopened.damaged] == ["ev-bad"]


def test_the_store_rules_still_apply_through_the_cache(tmp_path: Path) -> None:
    cache = EvidenceCache(EvidenceStore(tmp_path / "run", ToolRunStore(tmp_path / "run")))

    with pytest.raises(EvidenceNotAllowed):
        cache.put(evidence())
    assert not cache.has(key())


def test_the_cache_answers_the_reconciliation_of_a_tool_run(
    stores: tuple[ToolRunStore, EvidenceStore],
) -> None:
    cache = EvidenceCache(stores[1])
    assert reconcile_run_tool(cache, key()).decision is Decision.REDO

    cache.put(evidence())

    assert reconcile_run_tool(cache, key()).decision is Decision.ALREADY_DONE
