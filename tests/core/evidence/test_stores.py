import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from forja.core.events.models import Ref, RefKind
from forja.core.evidence import (
    Evidence,
    EvidenceNotAllowed,
    EvidenceStore,
    ToolRun,
    ToolRunStore,
)
from forja.core.process import Outcome, ProcessSpec
from forja.core.records import (
    RecordCorrupt,
    RecordExists,
    RecordMissing,
    UnsupportedRecordVersion,
)
from tests.core.evidence.test_models import evidence
from tests.core.process.support import minimal_env, run_to_end, spec


@pytest.fixture
def runs(tmp_path: Path) -> ToolRunStore:
    return ToolRunStore(tmp_path / "run")


@pytest.fixture
def evidences(tmp_path: Path, runs: ToolRunStore) -> EvidenceStore:
    return EvidenceStore(tmp_path / "run", runs)


def record_run(
    runs: ToolRunStore, tmp_path: Path, record_id: str = "run1", **spec_kwargs: Any
) -> Ref:
    process_spec = spec(spec_kwargs.pop("code", "print('measured')"), **spec_kwargs)
    result, _ = run_to_end(process_spec, tmp_path / f"{record_id}.log")
    return runs.record(record_id, "op1", process_spec, result)


# -- tool runs ---------------------------------------------------------------------------------


def test_a_tool_run_keeps_the_command_the_outcome_and_the_log_hash(
    runs: ToolRunStore, tmp_path: Path
) -> None:
    ref = record_run(runs, tmp_path, SECRET="s3cr3t")

    run = runs.get("run1")
    assert (ref.kind, ref.id) == (RefKind.TOOL_RUN, "run1")
    assert run.outcome is Outcome.EXITED and run.exit_code == 0
    assert run.operation_id == "op1" and run.duration_seconds >= 0
    assert run.command[1] == "-c"
    assert "SECRET" in run.env_names
    assert "s3cr3t" not in (tmp_path / "run" / "tool_runs" / "run1.json").read_text()
    assert run.log_sha256 == hashlib.sha256((tmp_path / "run1.log").read_bytes()).hexdigest()


def test_a_command_that_never_started_has_no_log_hash(runs: ToolRunStore, tmp_path: Path) -> None:
    missing = ProcessSpec(["forja-no-such-binary"], tmp_path, minimal_env(), timeout=5)
    result, _ = run_to_end(missing, tmp_path / "never.log")

    runs.record("run2", "op2", missing, result)

    run = runs.get("run2")
    assert (run.outcome, run.exit_code, run.log_sha256) == (Outcome.SPAWN_FAILED, None, None)


def test_the_reference_is_the_id_and_the_hash_of_the_stored_bytes(
    runs: ToolRunStore, tmp_path: Path
) -> None:
    ref = record_run(runs, tmp_path)

    stored = (tmp_path / "run" / "tool_runs" / "run1.json").read_bytes()
    assert ref.hash == hashlib.sha256(stored).hexdigest()
    runs.verify(ref)


def test_a_changed_or_deleted_record_fails_verification(runs: ToolRunStore, tmp_path: Path) -> None:
    ref = record_run(runs, tmp_path)
    path = tmp_path / "run" / "tool_runs" / "run1.json"
    path.write_bytes(path.read_bytes().replace(b'"exit_code":0', b'"exit_code":1'))

    with pytest.raises(RecordCorrupt, match="differs"):
        runs.verify(ref)
    path.unlink()
    with pytest.raises(RecordMissing):
        runs.verify(ref)


def test_a_reference_of_another_kind_is_not_accepted(runs: ToolRunStore, tmp_path: Path) -> None:
    ref = record_run(runs, tmp_path)

    with pytest.raises(ValueError, match="not a tool_run reference"):
        runs.verify(Ref(kind=RefKind.EVIDENCE, id=ref.id, hash=ref.hash))


def test_recording_the_same_run_twice_changes_nothing_but_a_different_one_is_refused(
    runs: ToolRunStore, tmp_path: Path
) -> None:
    first = record_run(runs, tmp_path)
    run = runs.get("run1")

    assert runs.put(run) == first
    with pytest.raises(RecordExists):
        runs.put(ToolRun.model_validate({**run.model_dump(mode="json"), "exit_code": 9}))


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "NUL"])
def test_record_ids_are_safe_file_names(runs: ToolRunStore, bad: str) -> None:
    with pytest.raises(ValueError):
        runs.get(bad)


def test_a_missing_record_is_reported_and_a_damaged_one_is_corrupt(
    runs: ToolRunStore, tmp_path: Path
) -> None:
    with pytest.raises(RecordMissing):
        runs.get("ghost")
    record_run(runs, tmp_path)
    path = tmp_path / "run" / "tool_runs" / "run1.json"

    path.write_bytes(b"garbage")
    with pytest.raises(RecordCorrupt, match="not valid JSON"):
        runs.get("run1")
    path.write_bytes(b"[]")
    with pytest.raises(RecordCorrupt, match="not a JSON object"):
        runs.get("run1")
    path.write_bytes(b'{"id":"run1"}')
    with pytest.raises(RecordCorrupt, match="schema_version"):
        runs.get("run1")


def test_a_record_stored_under_another_name_is_corrupt(runs: ToolRunStore, tmp_path: Path) -> None:
    record_run(runs, tmp_path)
    folder = tmp_path / "run" / "tool_runs"
    (folder / "run1.json").rename(folder / "run9.json")

    with pytest.raises(RecordCorrupt, match="file name"):
        runs.get("run9")


def test_a_newer_schema_version_is_refused(runs: ToolRunStore, tmp_path: Path) -> None:
    record_run(runs, tmp_path)
    path = tmp_path / "run" / "tool_runs" / "run1.json"
    path.write_text(path.read_text().replace('"schema_version":1', '"schema_version":2'))

    with pytest.raises(UnsupportedRecordVersion, match="upgrade Forja"):
        runs.get("run1")


def test_an_older_record_is_converted_on_read(tmp_path: Path) -> None:
    root = tmp_path / "run"
    old = {
        "schema_version": 0,
        "id": "run1",
        "operation_id": "op1",
        "command_line": ["tool", "--x"],  # version 0 stored the command under another name
        "cwd": "/w",
        "env_names": [],
        "outcome": "exited",
        "exit_code": 0,
        "duration_seconds": 1.0,
        "log_path": "/w/log",
        "log_sha256": None,
    }
    (root / "tool_runs").mkdir(parents=True)
    (root / "tool_runs" / "run1.json").write_text(json.dumps(old))

    def upgrade(record: dict[str, Any]) -> dict[str, Any]:
        record["command"] = record.pop("command_line")
        return record

    assert ToolRunStore(root, upgraders={0: upgrade}).get("run1").command == ("tool", "--x")
    with pytest.raises(UnsupportedRecordVersion):
        ToolRunStore(root).get("run1")


def test_a_crash_while_writing_leaves_no_record(tmp_path: Path) -> None:
    def crash(path: Path, data: bytes) -> None:
        raise OSError("disk gone")

    runs = ToolRunStore(tmp_path / "run", write=crash)
    result, _ = run_to_end(spec("pass"), tmp_path / "x.log")
    with pytest.raises(OSError):
        runs.record("run1", "op1", spec("pass"), result)

    with pytest.raises(RecordMissing):
        ToolRunStore(tmp_path / "run").get("run1")


# -- evidence ----------------------------------------------------------------------------------


def test_evidence_is_stored_and_read_back_with_its_reference(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    record_run(runs, tmp_path)

    ref = evidences.put(evidence())

    assert (ref.kind, ref.id) == (RefKind.EVIDENCE, "ev1")
    assert evidences.get("ev1") == evidence()
    evidences.verify(ref)


def test_evidence_needs_a_known_tool_run(evidences: EvidenceStore) -> None:
    with pytest.raises(EvidenceNotAllowed, match="unknown tool run 'run1'"):
        evidences.put(evidence())


@pytest.mark.parametrize(
    ("timeout", "outcome"),
    [(0.5, "timed_out")],
)
def test_a_tool_run_that_did_not_finish_cannot_produce_evidence(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path, timeout: float, outcome: str
) -> None:
    process_spec = spec("import time; time.sleep(60)", timeout=timeout, grace=0.5)
    result, _ = run_to_end(process_spec, tmp_path / "slow.log")
    runs.record("run1", "op1", process_spec, result)

    with pytest.raises(EvidenceNotAllowed, match=outcome):
        evidences.put(evidence())


def test_a_command_that_never_started_cannot_produce_evidence(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    missing = ProcessSpec(["forja-no-such-binary"], tmp_path, minimal_env(), timeout=5)
    result, _ = run_to_end(missing, tmp_path / "never.log")
    runs.record("run1", "op1", missing, result)

    with pytest.raises(EvidenceNotAllowed, match="spawn_failed"):
        evidences.put(evidence())


def test_a_non_zero_exit_code_alone_does_not_forbid_evidence(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    record_run(runs, tmp_path, code="raise SystemExit(3)")

    evidences.put(evidence())

    assert runs.get("run1").exit_code == 3


def test_evidence_cannot_be_rewritten(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    record_run(runs, tmp_path)
    first = evidences.put(evidence())

    assert evidences.put(evidence()) == first
    with pytest.raises(RecordExists):
        evidences.put(evidence(value=8))


def test_changed_evidence_fails_verification(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    record_run(runs, tmp_path)
    ref = evidences.put(evidence())
    path = tmp_path / "run" / "evidence" / "ev1.json"
    path.write_bytes(path.read_bytes().replace(b'"value":7', b'"value":1'))

    with pytest.raises(RecordCorrupt):
        evidences.verify(ref)


def test_evidence_store_returns_evidence_objects(
    runs: ToolRunStore, evidences: EvidenceStore, tmp_path: Path
) -> None:
    record_run(runs, tmp_path)
    evidences.put(evidence())

    assert isinstance(evidences.get("ev1"), Evidence)


def test_a_tool_run_records_where_it_ran_and_where_its_log_is(
    runs: ToolRunStore, tmp_path: Path
) -> None:
    process_spec = spec("print('x')")
    result, _ = run_to_end(process_spec, tmp_path / "where.log")

    runs.record("run1", "op1", process_spec, result)

    run = runs.get("run1")
    assert run.cwd == str(process_spec.cwd)
    assert run.log_path == str(tmp_path / "where.log")


def test_the_evidence_store_passes_its_options_on_to_the_record_store(tmp_path: Path) -> None:
    written: list[Path] = []

    def spy(path: Path, data: bytes) -> None:
        written.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    runs = ToolRunStore(tmp_path / "run")
    record_run(runs, tmp_path)
    EvidenceStore(tmp_path / "run", runs, write=spy).put(evidence(id="ev1"))

    assert [p.name for p in written] == ["ev1.json"]


def test_the_evidence_store_converts_older_records_with_the_upgraders_it_was_given(
    tmp_path: Path,
) -> None:
    runs = ToolRunStore(tmp_path / "run")
    record_run(runs, tmp_path)
    EvidenceStore(tmp_path / "run", runs).put(evidence(id="ev1"))
    path = tmp_path / "run" / "evidence" / "ev1.json"
    path.write_text(path.read_text().replace('"schema_version":1', '"schema_version":0'))

    def upgrade(record: dict[str, Any]) -> dict[str, Any]:
        return record

    assert EvidenceStore(tmp_path / "run", runs, upgraders={0: upgrade}).get("ev1").id == "ev1"
    with pytest.raises(UnsupportedRecordVersion):
        EvidenceStore(tmp_path / "run", runs).get("ev1")
