from pathlib import Path

import pytest

from forja.core.adapters import (
    AdapterRegistry,
    AdapterRejected,
    Detection,
    DiscoverySpec,
    FileClass,
    LanguageCapability,
    ProbeTask,
    TemplateExecutorAdapter,
)
from tests.core.adapters.fakes import FakeExecutorAdapter, FakeLanguageAdapter


class GoAdapter(FakeLanguageAdapter):
    language = "go"
    grammar = "go"

    def detect(self, root: Path) -> Detection | None:
        if not (root / "go.mod").is_file():
            return None
        return Detection("go", (".",), ("go.mod",))

    def classify(self, path: str) -> FileClass | None:
        return FileClass.PRODUCTION if path.endswith(".go") else None


class OldAdapter(FakeLanguageAdapter):
    contract_version = 0


def test_adapters_are_found_by_name() -> None:
    registry = AdapterRegistry()
    language, executor = FakeLanguageAdapter(), FakeExecutorAdapter()

    registry.register_language(language)
    registry.register_executor(executor)

    assert registry.language("python") is language
    assert registry.executor("fake-agent") is executor
    assert list(registry.languages()) == [language] and list(registry.executors()) == [executor]
    with pytest.raises(KeyError):
        registry.language("rust")


def test_the_same_language_or_executor_cannot_be_registered_twice() -> None:
    registry = AdapterRegistry()
    registry.register_language(FakeLanguageAdapter())
    registry.register_executor(FakeExecutorAdapter())

    with pytest.raises(AdapterRejected, match="already registered"):
        registry.register_language(FakeLanguageAdapter())
    with pytest.raises(AdapterRejected, match="already registered"):
        registry.register_executor(FakeExecutorAdapter())


def test_unsupported_languages_and_other_contract_versions_are_refused() -> None:
    registry = AdapterRegistry()

    class Cobol(FakeLanguageAdapter):
        language = "cobol"

    with pytest.raises(AdapterRejected, match="not a supported language"):
        registry.register_language(Cobol())
    with pytest.raises(AdapterRejected, match="speaks contract 0"):
        registry.register_language(OldAdapter())

    class OldAgent(FakeExecutorAdapter):
        contract_version = 7

    with pytest.raises(AdapterRejected, match="speaks contract 7"):
        registry.register_executor(OldAgent())


def test_capabilities_must_be_real_capabilities() -> None:
    class Sloppy(FakeLanguageAdapter):
        capabilities = frozenset({"coverage"})  # type: ignore[arg-type]

    with pytest.raises(AdapterRejected, match="LanguageCapability"):
        AdapterRegistry().register_language(Sloppy())
    assert LanguageCapability.COVERAGE.value == "coverage"


def test_an_executor_needs_a_name() -> None:
    nameless = TemplateExecutorAdapter(
        "",
        DiscoverySpec(("x",)),
        ("{executable}", "{package}"),
        ProbeTask("p", "f", "c", frozenset()),
    )

    with pytest.raises(AdapterRejected, match="empty"):
        AdapterRegistry().register_executor(nameless)


def test_every_language_found_in_the_repository_is_reported_in_registration_order(
    tmp_path: Path,
) -> None:
    registry = AdapterRegistry()
    registry.register_language(FakeLanguageAdapter())
    registry.register_language(GoAdapter())
    (tmp_path / "pyproject.toml").write_text("")

    assert [d.language for _, d in registry.detect_all(tmp_path)] == ["python"]
    (tmp_path / "go.mod").write_text("")
    assert [d.language for _, d in registry.detect_all(tmp_path)] == ["python", "go"]


def test_the_first_adapter_that_claims_a_file_decides_and_unclaimed_files_are_other() -> None:
    registry = AdapterRegistry()
    registry.register_language(FakeLanguageAdapter())
    registry.register_language(GoAdapter())

    assert registry.classify("src/app.py") is FileClass.PRODUCTION
    assert registry.classify("tests/test_app.py") is FileClass.TEST
    assert registry.classify("cmd/main.go") is FileClass.PRODUCTION
    assert registry.classify("package-lock.json") is FileClass.OTHER
    assert registry.classify("") is FileClass.OTHER
    assert AdapterRegistry().classify("anything.py") is FileClass.OTHER
