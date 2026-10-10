import logging
import time

import pytest

import forja.core.redaction.engine as engine_module
from forja.core.isolation import SensitivePaths
from forja.core.redaction import (
    LONG_LINE_MASK,
    Category,
    DropReason,
    ItemKind,
    PackageItem,
    Redactor,
    is_essential,
)
from tests.core.redaction.corpus import secrets

SECRET = next(p.secret for p in secrets() if p.rule == "github-token")


def file(name: str, content: str, *, essential: bool = False) -> PackageItem:
    return PackageItem(ItemKind.FILE, name, content, essential)


# -- whole items that are withheld -------------------------------------------------------------


def test_files_marked_sensitive_never_go_out() -> None:
    result = Redactor().redact([file("src/app.py", "x = 1"), file("config/.env", "A=1")])

    assert [i.name for i in result.items] == ["src/app.py"]
    assert [(d.name, d.reason) for d in result.dropped] == [
        ("config/.env", DropReason.SENSITIVE_FILE)
    ]


def test_a_repositorys_own_sensitive_patterns_apply() -> None:
    redactor = Redactor(
        sensitive=SensitivePaths.with_defaults(["vault/**"], case_insensitive=False)
    )

    result = redactor.redact([file("vault/data.txt", "x")])

    assert result.items == () and result.dropped[0].reason is DropReason.SENSITIVE_FILE


def test_only_files_are_judged_by_name_so_evidence_called_dot_env_is_not_dropped() -> None:
    items = [
        PackageItem(ItemKind.EVIDENCE, ".env", "value 3"),
        PackageItem(ItemKind.TEXT, "id_rsa", "x"),
    ]

    result = Redactor().redact(items)

    assert [i.name for i in result.items] == [".env", "id_rsa"] and result.dropped == ()


def test_binary_content_is_withheld() -> None:
    result = Redactor().redact([file("logo.bin", "ab" + chr(0) + "cd")])

    assert result.items == () and result.dropped[0].reason is DropReason.BINARY


def test_an_item_over_the_size_limit_is_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "MAX_ITEM_CHARS", 100)

    result = Redactor().redact([file("big.txt", "x" * 101), file("ok.txt", "x" * 100)])

    assert [i.name for i in result.items] == ["ok.txt"]
    assert result.dropped[0].reason is DropReason.TOO_LARGE


def test_a_very_long_line_is_replaced_not_scanned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "MAX_LINE_CHARS", 50)
    text = "short\n" + "m" * 60 + "\nalso short\n"

    result = Redactor().redact([file("bundle.js", text)])

    assert result.items[0].content == f"short\n{LONG_LINE_MASK}\nalso short\n"
    assert [(f.category, f.line) for f in result.findings] == [(Category.LONG_LINE, 2)]


# -- failing closed ----------------------------------------------------------------------------


def test_an_item_that_makes_the_redactor_fail_is_withheld_never_sent_as_it_was(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    original = Redactor._mask

    def explode(self: Redactor, item: PackageItem, *args: object) -> object:
        if item.name == "bad.py":
            raise RuntimeError("boom")
        return original(self, item, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(Redactor, "_mask", explode)
    items = [
        file("good.py", f"t = {SECRET}"),
        file("bad.py", f"t = {SECRET}"),
        file("last.py", "x"),
    ]

    with caplog.at_level(logging.ERROR, logger="forja.redaction"):
        result = Redactor().redact(items)

    assert [i.name for i in result.items] == ["good.py", "last.py"]
    assert [(d.name, d.reason) for d in result.dropped] == [("bad.py", DropReason.ERROR)]
    assert SECRET not in "".join(i.content for i in result.items)
    assert "bad.py" in caplog.text and SECRET not in caplog.text


# -- what the model is told it is missing ------------------------------------------------------


def test_withholding_an_essential_file_becomes_a_declared_assumption() -> None:
    result = Redactor().redact([file("config/.env", "A=1", essential=True)])

    (assumption,) = result.assumptions
    assert assumption.statement == "The content of config/.env was withheld from the model"
    assert assumption.reason == "it matches the sensitive-file patterns"
    assert assumption.missing_evidence == "the content of config/.env"


def test_masking_inside_an_essential_file_becomes_an_assumption_naming_the_rules_only() -> None:
    result = Redactor().redact([file("src/client.py", f"token = '{SECRET}'", essential=True)])

    (assumption,) = result.assumptions
    assert "src/client.py" in assumption.statement
    assert "github-token" in assumption.reason
    assert SECRET not in str(assumption)


def test_things_that_are_not_essential_make_no_assumption() -> None:
    items = [file("config/.env", "A=1"), file("src/client.py", f"t = {SECRET}")]

    assert Redactor().redact(items).assumptions == ()


def test_a_clean_essential_file_makes_no_assumption() -> None:
    assert Redactor().redact([file("src/ok.py", "x = 1", essential=True)]).assumptions == ()


def test_a_file_is_essential_if_it_is_in_scope_or_cited() -> None:
    assert is_essential("src/a.py", scope=["src/a.py"], cited_paths=[])
    assert is_essential("src/b.py", scope=[], cited_paths=["src/b.py"])
    assert is_essential("src\\a.py", scope=["src/a.py"], cited_paths=[])
    assert not is_essential("src/c.py", scope=["src/a.py"], cited_paths=["src/b.py"])


# -- order, kinds, and the result --------------------------------------------------------------


def test_items_keep_their_order_and_kind() -> None:
    items = [
        PackageItem(ItemKind.TEXT, "intro", "hello"),
        file("src/a.py", "a"),
        PackageItem(ItemKind.EVIDENCE, "ev1", "3"),
    ]

    result = Redactor().redact(items)

    assert [(i.kind, i.name) for i in result.items] == [
        (ItemKind.TEXT, "intro"),
        (ItemKind.FILE, "src/a.py"),
        (ItemKind.EVIDENCE, "ev1"),
    ]


def test_the_result_says_which_rules_were_used() -> None:
    from forja.core.redaction import rules_version

    assert Redactor().redact([]).rules_version == rules_version()
    assert Redactor().redact([]).items == ()


# -- hostile input must not hang the redactor --------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("a" * 19_999 + "\n", id="long plain line"),
        pytest.param("api_key=" * 20_000, id="many keywords"),
        pytest.param("-----BEGIN RSA PRIVATE KEY-----\n" + "A1b2" * 400 + "\n", id="open key"),
        pytest.param(
            ("-----BEGIN PRIVATE KEY-----" + "Qw1" * 600 + "\n") * 150, id="many open keys"
        ),
        pytest.param("1 " * 100_000, id="digits and spaces"),
        pytest.param("9" * 200_000, id="digit run"),
        pytest.param("@" * 100_000, id="at signs"),
        pytest.param("a@" * 50_000, id="local parts"),
        pytest.param("password=" + "x;" * 100_000, id="password terminators"),
        pytest.param("://" * 50_000, id="schemes"),
        pytest.param("(" * 100_000, id="parentheses"),
    ],
)
def test_pathological_input_is_handled_in_reasonable_time(text: str) -> None:
    started = time.monotonic()

    Redactor().redact([PackageItem(ItemKind.TEXT, "x", text)])

    assert time.monotonic() - started < 10
