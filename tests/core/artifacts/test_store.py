import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from forja.core.artifacts import (
    ArtifactCorrupt,
    ArtifactExists,
    ArtifactHeader,
    ArtifactMissing,
    ArtifactStore,
    ArtifactType,
    Assumption,
    ChangeDeclaration,
    DeclaredChange,
    Executor,
    InputMismatch,
    InputRef,
    Producer,
    SchemaNotDefined,
    UnsupportedArtifactVersion,
)
from forja.core.artifacts.llm_output import Action, DeclaredFile
from forja.core.events import RefKind
from forja.core.events.models import Ref

CLI = Executor(cli="claude-code", version="2.1.0")
COMMIT = "a" * 40


def declaration(summary: str = "add parser") -> ChangeDeclaration:
    return ChangeDeclaration(
        actions=(
            Action(
                summary=summary,
                reason="needed by the task",
                files=(DeclaredFile(path="src/parser.py", change=DeclaredChange.CREATED),),
            ),
        )
    )


def put(store: ArtifactStore, **overrides: Any) -> ArtifactHeader:
    args: dict[str, Any] = {
        "artifact_type": ArtifactType.CHANGE_DECLARATION,
        "producer": Producer.IMPLEMENTER,
        "executor": CLI,
        "attempt_id": "att1",
        "base_commit": COMMIT,
        "body": declaration(),
    }
    args.update(overrides)
    return store.put(**args)


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "run")


def test_put_then_get_returns_header_and_typed_body(store: ArtifactStore) -> None:
    header = put(store, assumptions=[Assumption(statement="s", reason="r", missing_evidence="e")])

    stored = store.get(header.id)

    assert stored.header == header
    assert stored.body == declaration()
    assert header.executor == CLI and header.attempt_id == "att1" and header.base_commit == COMMIT
    assert header.assumptions[0].missing_evidence == "e"


def test_body_is_stored_by_the_hash_of_its_canonical_bytes(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store)

    blob = tmp_path / "run" / "blobs" / header.content_hash
    assert hashlib.sha256(blob.read_bytes()).hexdigest() == header.content_hash
    assert b" " not in blob.read_bytes().replace(b"add parser", b"").replace(
        b"needed by the task", b""
    )
    assert (tmp_path / "run" / "artifacts" / f"{header.id}.json").exists()


def test_equal_bodies_share_one_blob_but_keep_separate_headers(
    store: ArtifactStore, tmp_path: Path
) -> None:
    first, second = put(store), put(store, attempt_id="att2")

    assert first.id != second.id
    assert first.content_hash == second.content_hash
    assert len(list((tmp_path / "run" / "blobs").iterdir())) == 1


def test_repeating_a_put_with_the_same_id_and_content_changes_nothing(store: ArtifactStore) -> None:
    first = put(store, artifact_id="fixed1")

    assert put(store, artifact_id="fixed1") == first


def test_reusing_an_id_for_a_different_artifact_is_refused(store: ArtifactStore) -> None:
    put(store, artifact_id="fixed1")

    with pytest.raises(ArtifactExists):
        put(store, artifact_id="fixed1", body=declaration("something else"))


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "", "-x", "CON", "nul", "com1", "a b"])
def test_ids_that_are_unsafe_as_file_names_are_refused(store: ArtifactStore, bad: str) -> None:
    with pytest.raises(ValueError):
        put(store, artifact_id=bad)
    with pytest.raises(ValueError):
        store.header(bad)


def test_a_role_needs_an_executor_and_forja_must_not_have_one(store: ArtifactStore) -> None:
    with pytest.raises(ValueError, match="needs its executor"):
        put(store, executor=None)
    with pytest.raises(ValueError, match="no executor"):
        put(store, producer=Producer.FORJA)

    forja_made = put(store, producer=Producer.FORJA, executor=None, attempt_id=None)
    assert forja_made.executor is None


def test_a_commit_must_be_a_full_hex_hash(store: ArtifactStore) -> None:
    with pytest.raises(ValueError):
        put(store, base_commit="main")
    assert put(store, base_commit=None).base_commit is None


def test_every_artifact_type_has_a_body_schema() -> None:
    from forja.core.artifacts import BODY_MODELS

    assert set(BODY_MODELS) == set(ArtifactType)


def test_a_type_without_a_schema_is_refused(
    store: ArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import forja.core.artifacts.store as store_module

    monkeypatch.setattr(store_module, "BODY_MODELS", {})

    with pytest.raises(SchemaNotDefined, match="change_declaration"):
        put(store)


def test_the_body_must_be_of_the_type_declared(store: ArtifactStore) -> None:
    with pytest.raises(TypeError, match="ChangeDeclaration"):
        put(store, body=CLI)


def test_inputs_are_pinned_by_hash_and_must_exist(store: ArtifactStore) -> None:
    base = put(store)
    good = InputRef(artifact_id=base.id, content_hash=base.content_hash)

    derived = put(store, inputs=[good], body=declaration("second"))
    assert store.header(derived.id).inputs == (good,)

    with pytest.raises(InputMismatch, match="another content hash"):
        put(store, inputs=[InputRef(artifact_id=base.id, content_hash="0" * 64)])
    with pytest.raises(InputMismatch, match="cannot be used"):
        put(store, inputs=[InputRef(artifact_id="ghost", content_hash=base.content_hash)])
    with pytest.raises(ValueError, match="listed twice"):
        put(store, inputs=[good, good])


def test_an_input_whose_body_was_damaged_cannot_be_used(
    store: ArtifactStore, tmp_path: Path
) -> None:
    base = put(store)
    (tmp_path / "run" / "blobs" / base.content_hash).write_bytes(b"{}")

    with pytest.raises(InputMismatch):
        put(store, inputs=[InputRef(artifact_id=base.id, content_hash=base.content_hash)])


def test_unknown_artifact_is_reported_as_missing(store: ArtifactStore) -> None:
    with pytest.raises(ArtifactMissing, match="header"):
        store.get("ghost")


def test_a_deleted_body_is_reported_as_missing(store: ArtifactStore, tmp_path: Path) -> None:
    header = put(store)
    (tmp_path / "run" / "blobs" / header.content_hash).unlink()

    with pytest.raises(ArtifactMissing, match="body"):
        store.get(header.id)


def test_a_changed_body_is_reported_as_corrupt(store: ArtifactStore, tmp_path: Path) -> None:
    header = put(store)
    blob = tmp_path / "run" / "blobs" / header.content_hash
    blob.write_bytes(blob.read_bytes().replace(b"add parser", b"add parsex"))

    with pytest.raises(ArtifactCorrupt, match="content hash"):
        store.get(header.id)


def test_a_damaged_header_is_reported_as_corrupt(store: ArtifactStore, tmp_path: Path) -> None:
    header = put(store)
    path = tmp_path / "run" / "artifacts" / f"{header.id}.json"

    path.write_bytes(b"not json")
    with pytest.raises(ArtifactCorrupt, match="not valid JSON"):
        store.get(header.id)

    record = json.loads(header.model_dump_json())
    record["producer"] = "nobody"
    path.write_bytes(json.dumps(record).encode())
    with pytest.raises(ArtifactCorrupt, match="header"):
        store.get(header.id)


def test_a_header_moved_to_another_file_name_is_corrupt(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store)
    folder = tmp_path / "run" / "artifacts"
    (folder / f"{header.id}.json").rename(folder / "other1.json")

    with pytest.raises(ArtifactCorrupt, match="file name"):
        store.get("other1")


def test_a_body_that_no_longer_fits_the_schema_is_corrupt(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store)
    forged = b'{"actions":[],"claims":[],"surprise":1}'
    new_hash = hashlib.sha256(forged).hexdigest()
    (tmp_path / "run" / "blobs" / new_hash).write_bytes(forged)
    path = tmp_path / "run" / "artifacts" / f"{header.id}.json"
    record = json.loads(path.read_bytes())
    record["content_hash"] = new_hash
    path.write_bytes(json.dumps(record).encode())

    with pytest.raises(ArtifactCorrupt, match="body"):
        store.get(header.id)


def test_event_references_carry_id_and_hash_and_can_be_verified(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store)
    ref = store.ref(header)

    assert (ref.kind, ref.id, ref.hash) == (RefKind.ARTIFACT, header.id, header.content_hash)
    store.verify(ref)

    with pytest.raises(ArtifactCorrupt, match="differs"):
        store.verify(Ref(kind=RefKind.ARTIFACT, id=header.id, hash="1" * 64))
    with pytest.raises(ValueError, match="not an artifact"):
        store.verify(Ref(kind=RefKind.EVIDENCE, id=header.id, hash=header.content_hash))
    (tmp_path / "run" / "blobs" / header.content_hash).unlink()
    with pytest.raises(ArtifactMissing):
        store.verify(ref)


# -- interrupted or failing writes -------------------------------------------------------------


def _failing_second_write(real: Callable[[Path, bytes], None]) -> Callable[[Path, bytes], None]:
    calls = 0

    def write(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("crash before the header is saved")
        real(path, data)

    return write


def test_a_crash_between_body_and_header_leaves_no_artifact_and_a_retry_succeeds(
    tmp_path: Path,
) -> None:
    from forja.core.atomic import atomic_write_bytes

    root = tmp_path / "run"
    crashing = ArtifactStore(root, write=_failing_second_write(atomic_write_bytes))
    with pytest.raises(OSError):
        put(crashing, artifact_id="fixed1")

    fresh = ArtifactStore(root)
    with pytest.raises(ArtifactMissing):
        fresh.get("fixed1")
    assert len(list((root / "blobs").iterdir())) == 1  # the orphan body is harmless

    header = put(fresh, artifact_id="fixed1")
    assert fresh.get("fixed1").header == header
    assert len(list((root / "blobs").iterdir())) == 1  # and it is reused


def test_a_half_written_body_is_rewritten_by_the_next_put(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store, artifact_id="first1")
    blob = tmp_path / "run" / "blobs" / header.content_hash
    blob.write_bytes(blob.read_bytes()[:10])

    again = put(store, artifact_id="second")

    assert store.get(again.id).body == declaration()


# -- schema versions ---------------------------------------------------------------------------


def _set_version(tmp_path: Path, artifact_id: str, version: int) -> None:
    path = tmp_path / "run" / "artifacts" / f"{artifact_id}.json"
    record = json.loads(path.read_bytes())
    record["schema_version"] = version
    path.write_bytes(json.dumps(record).encode())


def test_a_newer_schema_version_is_refused_not_misread(
    store: ArtifactStore, tmp_path: Path
) -> None:
    header = put(store)
    _set_version(tmp_path, header.id, 2)

    with pytest.raises(UnsupportedArtifactVersion, match="upgrade Forja"):
        store.get(header.id)


def test_an_older_artifact_is_converted_on_read_after_its_hash_is_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import forja.core.artifacts.store as store_module

    root = tmp_path / "run"
    header = put(ArtifactStore(root))
    _set_version(tmp_path, header.id, 0)

    def upgrade(record: dict[str, Any]) -> dict[str, Any]:
        record["body"].setdefault("claims", [])
        return record

    upgraded = ArtifactStore(root, upgraders={(ArtifactType.CHANGE_DECLARATION, 0): upgrade})
    monkeypatch.setattr(store_module, "ARTIFACT_SCHEMA_VERSION", 1)

    assert upgraded.get(header.id).body == declaration()
    with pytest.raises(UnsupportedArtifactVersion):
        ArtifactStore(root).get(header.id)  # no converter registered

    blob = root / "blobs" / header.content_hash
    blob.write_bytes(blob.read_bytes().replace(b"add parser", b"add parsex"))
    with pytest.raises(ArtifactCorrupt):
        upgraded.get(header.id)
