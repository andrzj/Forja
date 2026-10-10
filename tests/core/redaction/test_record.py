import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from forja.core.artifacts.models import Executor, Producer
from forja.core.events import Ref, RefKind
from forja.core.records import RecordCorrupt, RecordMissing
from forja.core.redaction import (
    ItemKind,
    PackageItem,
    RedactionResult,
    RedactionSettings,
    Redactor,
    SentPackageStore,
    canonical_package,
)
from tests.core.events.support import RUN, create_run, open_log
from tests.core.redaction.corpus import personal_data, secrets

MOMENT = datetime(2026, 10, 10, 15, 30, tzinfo=UTC)
EXECUTOR = Executor(cli="fake-agent", version="1.2.3")
PLANTED = secrets()
PEOPLE = personal_data()


def package() -> RedactionResult:
    items = [
        PackageItem(
            ItemKind.FILE, "src/client.py", "t = " + PLANTED[2].secret + "\n", essential=True
        ),
        PackageItem(ItemKind.FILE, "config/.env", "A=1"),
        PackageItem(ItemKind.EVIDENCE, "ev1", "contact " + PEOPLE[4].value),
        PackageItem(ItemKind.TEXT, "goal", "refactor the client"),
    ]
    return Redactor().redact(items)


def save(store: SentPackageStore, record_id: str = "pkg1", **changes: object) -> Ref:
    args: dict[str, object] = {
        "attempt_id": "att1",
        "role": Producer.IMPLEMENTER,
        "executor": EXECUTOR,
        "result": package(),
        "settings_digest": RedactionSettings().digest(),
        "created_at": MOMENT,
    }
    args.update(changes)
    return store.save(record_id, **args)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: Path) -> SentPackageStore:
    return SentPackageStore(tmp_path / "run")


def test_the_record_says_who_got_what_under_which_rules(store: SentPackageStore) -> None:
    result = package()

    ref = save(store, result=result)

    record = store.get("pkg1")
    assert (ref.kind, ref.id) == (RefKind.SENT_PACKAGE, "pkg1")
    assert (record.attempt_id, record.role, record.executor) == (
        "att1",
        Producer.IMPLEMENTER,
        EXECUTOR,
    )
    assert record.rules_version == result.rules_version
    assert record.settings_digest == RedactionSettings().digest()
    assert record.item_count == 3 and record.created_at == "2026-10-10T15:30:00.000000Z"
    assert (
        record.findings_by_rule == {"email": 1, "generic-credential": 1}
        or "github-token" in record.findings_by_rule
    )
    assert [(d.name, d.kind.value, d.reason.value) for d in record.dropped] == [
        ("config/.env", "file", "sensitive_file")
    ]
    store.verify(ref)


def test_the_package_is_kept_as_sent_and_checked_against_its_hash(store: SentPackageStore) -> None:
    result = package()
    save(store, result=result)

    content = store.read_package("pkg1")

    assert content == canonical_package(result.items)
    assert store.get("pkg1").package_hash == hashlib.sha256(content).hexdigest()
    sent = json.loads(content)
    assert [item["name"] for item in sent] == ["src/client.py", "ev1", "goal"]
    assert "[REDACTED:github-token:1]" in sent[0]["content"]


def test_nothing_that_was_masked_or_withheld_is_anywhere_on_disk(
    store: SentPackageStore, tmp_path: Path
) -> None:
    save(store)

    everything = b"".join(p.read_bytes() for p in (tmp_path / "run").rglob("*") if p.is_file())

    assert PLANTED[2].secret.encode() not in everything
    assert PEOPLE[4].value.encode() not in everything
    assert b"A=1" not in everything  # the withheld file's content


def test_the_record_holds_names_and_counts_never_values(store: SentPackageStore) -> None:
    save(store)

    record_text = (store._folder / "pkg1.json").read_text()  # noqa: SLF001

    assert PLANTED[2].secret not in record_text and PEOPLE[4].value not in record_text
    assert "config/.env" in record_text  # a name is not a secret


def test_a_package_changed_after_the_fact_is_detected(
    store: SentPackageStore, tmp_path: Path
) -> None:
    save(store)
    path = tmp_path / "run" / "sent_packages" / "pkg1.package"

    path.write_bytes(path.read_bytes().replace(b"refactor", b"deletes_"))
    with pytest.raises(RecordCorrupt, match="differs from its recorded hash"):
        store.read_package("pkg1")

    path.unlink()
    with pytest.raises(RecordMissing):
        store.read_package("pkg1")


def test_saving_the_same_package_again_changes_nothing_but_a_different_one_is_refused(
    store: SentPackageStore,
) -> None:
    first = save(store)

    assert save(store) == first
    with pytest.raises(Exception, match="holds a different record"):
        save(store, attempt_id="att2")


def test_the_digest_of_the_settings_in_force_is_recorded(store: SentPackageStore) -> None:
    custom = RedactionSettings(allow=("some-value",))
    save(store, "plain")
    save(store, "custom", settings_digest=custom.digest())

    assert store.get("plain").settings_digest != store.get("custom").settings_digest
    assert RedactionSettings().digest() == RedactionSettings().digest()


def test_a_roles_without_an_executor_can_be_recorded_for_forja_itself(
    store: SentPackageStore,
) -> None:
    save(store, role=Producer.FORJA, executor=None)

    assert store.get("pkg1").executor is None


def test_an_event_can_cite_what_was_sent(store: SentPackageStore, tmp_path: Path) -> None:
    from forja.core.states import ExecutionState, Level

    ref = save(store)

    with open_log(tmp_path / "events.jsonl") as log:
        create_run(log)
        event = log.append_transition(
            Level.EXECUTION, RUN, ExecutionState.PREPARING, ExecutionState.CONFIRMED, refs=[ref]
        )

    assert event.refs == (ref,)
