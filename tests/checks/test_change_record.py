"""The change record: symbols between two versions, proof of non-use, and the text it renders."""

from pathlib import Path

from forja.checks.change_record import (
    REASONS,
    RecordFacts,
    SymbolChange,
    file_changes,
    record_path,
    reference_proof,
    render_facts,
    render_record,
    symbol_changes,
    to_body,
)
from forja.checks.changes import Change, ChangeKind, Changes
from forja.core.artifacts.llm_output import (
    Claim,
    DeclaredChange,
    EvidenceCitation,
    FactCitation,
    FileCitation,
)
from forja.core.artifacts.models import Assumption, Executor
from forja.core.artifacts.schemas import ToolVersion

OLD = "def keep(): return 1\ndef change(): return 1\ndef _gone(): pass\ndef gone(): pass\n"
NEW = "def keep(): return 1\ndef change(): return 2\ndef fresh(): pass\n"
COMMIT = "a" * 40
NOBODY = "nenhum outro arquivo menciona o nome"


def changes_of(*changes: Change) -> Changes:
    return Changes(changes, 0, ())


def test_symbols_created_changed_and_removed_are_listed_per_file(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(NEW, encoding="utf-8")
    found, unreadable = symbol_changes(
        changes_of(Change(ChangeKind.MODIFIED, "m.py")), {"m.py": OLD}, tmp_path, {}
    )
    assert unreadable == ()
    assert [(s.name, s.change, s.public) for s in found] == [
        ("_gone", DeclaredChange.REMOVED, False),
        ("change", DeclaredChange.MODIFIED, True),
        ("fresh", DeclaredChange.CREATED, True),
        ("gone", DeclaredChange.REMOVED, True),
    ]


def test_an_added_file_creates_all_its_symbols_and_a_deleted_one_removes_them(
    tmp_path: Path,
) -> None:
    (tmp_path / "new.py").write_text("def a(): pass\n", encoding="utf-8")
    found, _ = symbol_changes(
        changes_of(Change(ChangeKind.ADDED, "new.py"), Change(ChangeKind.DELETED, "old.py")),
        {"old.py": "def b(): pass\n"},
        tmp_path,
        {},
    )
    assert [(s.path, s.name, s.change) for s in found] == [
        ("new.py", "a", DeclaredChange.CREATED),
        ("old.py", "b", DeclaredChange.REMOVED),
    ]


def test_a_renamed_file_is_compared_with_its_old_name(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("def a(): pass\ndef c(): pass\n", encoding="utf-8")
    found, _ = symbol_changes(
        changes_of(Change(ChangeKind.RENAMED, "b.py", "a.py")),
        {"a.py": "def a(): pass\n"},
        tmp_path,
        {},
    )
    assert [(s.name, s.change) for s in found] == [("c", DeclaredChange.CREATED)]


def test_a_file_that_is_not_code_is_left_out(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    found, unreadable = symbol_changes(
        changes_of(Change(ChangeKind.MODIFIED, "README.md")), {"README.md": "# y\n"}, tmp_path, {}
    )
    assert (found, unreadable) == ((), ())


def test_a_source_file_that_does_not_parse_is_reported_not_taken_for_empty(
    tmp_path: Path,
) -> None:
    (tmp_path / "m.py").write_text("def (:\n", encoding="utf-8")
    found, unreadable = symbol_changes(
        changes_of(Change(ChangeKind.MODIFIED, "m.py")), {"m.py": "def a(): pass\n"}, tmp_path, {}
    )
    assert (found, unreadable) == ((), ("m.py",))


def test_a_removed_symbol_carries_the_proof_of_who_still_mentions_it(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def keep(): pass\n", encoding="utf-8")
    others = {"m.py": "gone()", "other.py": "call_gone_not()", "use.py": "x = gone()"}
    found, _ = symbol_changes(
        changes_of(Change(ChangeKind.MODIFIED, "m.py")),
        {"m.py": "def keep(): pass\ndef gone(): pass\n"},
        tmp_path,
        others,
    )
    assert found[0].proof == "ainda mencionado em `use.py`"


def test_the_proof_is_a_whole_word_and_ignores_the_file_itself() -> None:
    proof = reference_proof("A.run", "a.py", {"a.py": "run()", "b.py": "running rerun"})
    assert proof == NOBODY


def test_the_proof_names_at_most_five_files() -> None:
    others = {f"f{i}.py": "run" for i in range(8)}
    assert reference_proof("run", "a.py", others).endswith("`f4.py` e mais 3")


def test_the_proof_looks_for_the_last_part_of_a_qualified_name() -> None:
    proof = reference_proof("A.run", "a.py", {"b.py": "x.run()"})
    assert proof == "ainda mencionado em `b.py`"


def test_exactly_five_files_are_all_named_with_nothing_more() -> None:
    others = {f"f{i}.py": "run" for i in range(5)}
    assert reference_proof("run", "a.py", others).endswith("`f4.py`")


def test_a_file_that_is_code_on_only_one_side_of_a_rename_is_not_left_out(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def a(): pass\n", encoding="utf-8")
    from_code = symbol_changes(
        changes_of(Change(ChangeKind.RENAMED, "b.txt", "a.py")),
        {"a.py": "def a(): pass\n"},
        tmp_path,
        {},
    )
    to_code = symbol_changes(
        changes_of(Change(ChangeKind.RENAMED, "b.py", "a.txt")), {"a.txt": "x\n"}, tmp_path, {}
    )
    assert from_code == ((), ("b.txt",))
    assert to_code == ((), ("b.py",))


def facts(**extra: object) -> RecordFacts:
    base: dict[str, object] = {
        "task_id": "t1",
        "intent": "reduce complexity of f",
        "files": file_changes(
            changes_of(Change(ChangeKind.MODIFIED, "b.py"), Change(ChangeKind.ADDED, "a.py"))
        ),
        "symbols": (
            SymbolChange("a.py", "f", "function", DeclaredChange.CREATED, True),
            SymbolChange("b.py", "g", "function", DeclaredChange.REMOVED, True, NOBODY),
        ),
        "metrics_before": {"max_ccn": 12.0},
        "metrics_after": {"max_ccn": 7.0, "functions": 3.0},
        "gates_passed": ("build", "tests"),
        "toolchains": (ToolVersion(name="python", version="3.12"),),
        "executors": (Executor(cli="claude", version="2.0"),),
        "revert_commit": COMMIT,
        "assumptions": (Assumption(statement="s", reason="r", missing_evidence="e"),),
    }
    return RecordFacts(**(base | extra))  # type: ignore[arg-type]


def test_the_facts_come_in_a_fixed_order_with_a_flag_on_a_public_removal() -> None:
    text = render_facts(facts())
    assert text.index("## Arquivos") < text.index("## Símbolos") < text.index("## Métricas")
    assert "- `a.py`: created\n- `b.py`: modified" in text
    assert "`g` (function) em `b.py`: removed; **símbolo público removido.** prova" in text
    assert "| max_ccn | 12 | 7 |" in text
    assert "| functions | - | 3 |" in text
    assert "- build\n- tests" in text
    assert "- python 3.12\n- CLI claude 2.0" in text
    assert "- s (motivo: r; faltou: e)" in text
    assert text.rstrip().endswith(f"`git revert {COMMIT}`")


def test_a_private_removal_is_not_flagged() -> None:
    symbol = SymbolChange("a.py", "_h", "function", DeclaredChange.REMOVED, False, "x")
    assert "símbolo público" not in render_facts(facts(symbols=(symbol,)))


def test_sections_with_nothing_say_so_and_unreadable_files_are_listed() -> None:
    text = render_facts(
        facts(
            symbols=(),
            gates_passed=(),
            assumptions=(),
            unreadable=("m.py",),
            metrics_before={},
            metrics_after={},
        )
    )
    assert "## Símbolos\n\nNenhum." in text
    assert "Símbolos não listados (arquivo ilegível):\n- `m.py`" in text
    assert "## Gates aprovados\n\nNenhum." in text
    assert "## Métricas\n\nNenhum." in text


def test_the_rendering_of_the_facts_does_not_depend_on_the_input_order() -> None:
    reordered = facts(files=tuple(reversed(facts().files)))
    assert render_facts(facts()) == render_facts(reordered)


def test_why_and_impact_hold_only_claims_with_their_citations() -> None:
    cited = FileCitation(kind="file", path="a.py", line_start=3, line_end=9)
    both = (
        EvidenceCitation(kind="evidence", evidence_id="ev1"),
        FactCitation(kind="fact", fact_id="fa1"),
    )
    claims = [
        Claim(statement="f was too branchy", citations=(cited,)),
        Claim(statement="max_ccn fell", citations=both),
    ]
    text = render_record(facts(), claims)
    assert text.startswith(render_facts(facts()))
    assert f"{REASONS}\n\n- f was too branchy (`a.py:3-9`)\n" in text
    assert "- max_ccn fell (evidência ev1; fato fa1)" in text


def test_without_claims_the_section_says_none() -> None:
    assert f"{REASONS}\n\nNenhum." in render_record(facts(), [])


def test_the_record_of_a_task_has_a_path_of_its_own() -> None:
    assert record_path("t7") == "docs/mudancas/t7.md"


def test_the_record_is_a_valid_artifact_body() -> None:
    body = to_body(facts())
    assert [f.path for f in body.files] == ["a.py", "b.py"]
    assert [s.name for s in body.symbols] == ["f", "g"]
    assert body.evidence_before == ("max_ccn=12",)
    assert body.evidence_after == ("functions=3", "max_ccn=7")
    assert body.revert_commit == COMMIT
