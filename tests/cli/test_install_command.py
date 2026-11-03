"""``forja instalar`` and the offer inside ``forja``: events, failures, and no network."""

import asyncio
import threading
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from forja.cli import install as installation
from forja.cli import main as door
from forja.cli.args import parse
from forja.cli.install import instalar, install_all, missing_tools, offer_line, run_install
from forja.cli.prepare import Refused
from forja.cli.settings import Execucao, Perfil
from forja.toolchain.install import Fetch
from forja.toolchain.manifest import Manifest
from forja.ui.install_events import InstallView, Stage
from tests.toolchain.test_install import manifest_for, zip_bytes

CONTENT = zip_bytes({"bin/tool": b"#!tool\n"})
ZIP_STAGES = [Stage.DOWNLOADING, Stage.CHECKSUM, Stage.EXTRACTING, Stage.VERIFYING, Stage.READY]


class Said:
    interactive = False

    def __init__(self) -> None:
        self.lines: list[str] = []

    def say(self, text: str = "") -> None:
        self.lines.append(text)

    def ask(self, question: str, *, default: str = "") -> str:
        return default

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class Recording:
    """An install screen that keeps every view it was shown."""

    def __init__(self) -> None:
        self.views: list[InstallView] = []

    def start(self, view: InstallView) -> None:
        self.views.append(view)

    def update(self, view: InstallView) -> None:
        self.views.append(view)

    def stop(self, view: InstallView) -> None:
        self.views.append(view)

    def stages(self, key: str = "tool") -> list[Stage]:
        seen: list[Stage] = []
        for view in self.views:
            stage = next(row.stage for row in view.tools if row.info.key == key)
            if not seen or seen[-1] is not stage:
                seen.append(stage)
        return seen


def serving() -> Fetch:
    def fetch(url: str, destination: Path, limit: int) -> None:
        destination.write_bytes(CONTENT)

    return fetch


def failing(url: str, destination: Path, limit: int) -> None:
    raise OSError("sem rede")


def on_path(folder: Path) -> str:
    for name in ("tool", "tool.exe"):
        (folder / name).write_text("x", encoding="utf-8")
        (folder / name).chmod(0o755)
    return str(folder)


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    return {"PATH": "", "FORJA_HOME": str(tmp_path / "home")}


@pytest.fixture
def manifest() -> Manifest:
    return manifest_for(CONTENT)


def test_a_tool_that_is_not_on_the_path_nor_installed_is_missing(
    environ: dict[str, str], manifest: Manifest
) -> None:
    assert [tool.name for tool in missing_tools(environ, manifest)] == ["tool"]


def test_a_tool_on_the_path_is_present(
    tmp_path: Path, environ: dict[str, str], manifest: Manifest
) -> None:
    assert missing_tools({**environ, "PATH": on_path(tmp_path)}, manifest) == []


def test_the_offer_names_the_tools_and_where_they_go(
    environ: dict[str, str], manifest: Manifest
) -> None:
    line = offer_line(missing_tools(environ, manifest), environ)
    assert "tool 1.2.3" in line
    assert str(Path(environ["FORJA_HOME"]) / "tools") in line


def test_the_installer_walks_a_tool_through_every_stage(
    environ: dict[str, str], manifest: Manifest
) -> None:
    screen = Recording()
    tools = missing_tools(environ, manifest)
    view = asyncio.run(install_all(tools, manifest, environ, screen, fetch=serving()))
    assert screen.stages() == [Stage.WAITING, *ZIP_STAGES]
    assert view.finished
    assert [row.info.key for row in view.summary.installed] == ["tool"]
    assert view.destination == str(Path(environ["FORJA_HOME"]) / "tools")
    info = view.tools[0].info
    assert (info.name, info.version, info.origin, info.size, info.purpose) == (
        "tool",
        "1.2.3",
        "example.org",
        len(CONTENT),
        "Faz algo.",
    )


def test_what_was_installed_is_no_longer_missing(
    environ: dict[str, str], manifest: Manifest
) -> None:
    tools = missing_tools(environ, manifest)
    asyncio.run(install_all(tools, manifest, environ, Recording(), fetch=serving()))
    assert missing_tools(environ, manifest) == []


def test_a_failed_download_is_told_with_its_reason_and_what_to_do(
    environ: dict[str, str], manifest: Manifest
) -> None:
    screen = Recording()
    tools = missing_tools(environ, manifest)
    view = asyncio.run(install_all(tools, manifest, environ, screen, fetch=failing))
    (row,) = view.summary.failed
    assert "sem rede" in row.reason
    assert row.fix == "rode `forja instalar` de novo; se persistir, instale tool à mão"
    assert screen.stages()[-1] is Stage.FAILED
    assert view.finished


def test_one_failing_tool_does_not_stop_the_next(environ: dict[str, str]) -> None:
    single = manifest_for(CONTENT)
    first = single.tools[0]
    both = single.model_copy(update={"tools": (first, first.model_copy(update={"name": "other"}))})
    served: list[str] = []

    def fetch(url: str, destination: Path, limit: int) -> None:
        served.append(url)
        if len(served) == 1:
            raise OSError("sem rede")
        destination.write_bytes(CONTENT)

    view = asyncio.run(install_all(list(both.tools), both, environ, Recording(), fetch=fetch))
    assert [row.info.key for row in view.summary.failed] == ["tool"]
    assert [row.info.key for row in view.summary.installed] == ["other"]
    assert len(served) == 2


def test_the_exit_code_says_whether_every_tool_is_in_place(
    environ: dict[str, str], manifest: Manifest
) -> None:
    tools = missing_tools(environ, manifest)
    bad = asyncio.run(
        run_install(tools, environ, Recording(), Said(), manifest=manifest, fetch=failing)
    )
    good = asyncio.run(
        run_install(tools, environ, Recording(), Said(), manifest=manifest, fetch=serving())
    )
    assert (bad, good) == (1, 0)


def test_the_download_reports_how_much_is_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installation, "POLL", 0.005)
    reports: list[int] = []
    seen = threading.Event()

    def fetch(url: str, destination: Path, limit: int) -> None:
        destination.write_bytes(b"12345")
        deadline = time.monotonic() + 5
        while 5 not in reports and time.monotonic() < deadline:
            time.sleep(0.005)
        if 5 in reports:
            seen.set()

    installation._watched(fetch, reports.append)("https://x", tmp_path / "f", 7)
    assert seen.is_set()


def test_the_command_says_when_there_is_nothing_to_install(
    tmp_path: Path, environ: dict[str, str], manifest: Manifest
) -> None:
    said = Said()
    code = asyncio.run(
        instalar(said, {**environ, "PATH": on_path(tmp_path)}, Perfil(), manifest=manifest)
    )
    assert code == 0
    assert "Nada a instalar" in said.text


def test_the_command_installs_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, environ: dict[str, str], manifest: Manifest
) -> None:
    screen = Recording()
    monkeypatch.setattr(installation, "install_renderer_for", lambda *_args: screen)
    code = asyncio.run(instalar(Said(), environ, Perfil(), manifest=manifest, fetch=serving()))
    assert code == 0
    assert screen.stages()[-1] is Stage.READY


def test_instalar_is_a_command() -> None:
    assert parse(["instalar"]).command == "instalar"


class Offer:
    """What ``door._install_offered`` called, in place of the real installation."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, code: int = 0) -> None:
        self.installed: list[str] = []
        self.code = code

        async def run(tools: list, *_args: object, **_kwargs: object) -> int:  # type: ignore[type-arg]
            self.installed += [tool.name for tool in tools]
            return self.code

        monkeypatch.setattr(door, "run_install", run)
        monkeypatch.setattr(door, "install_renderer_for", lambda *_args: Recording())
        monkeypatch.setattr(
            door, "refresh_environment", lambda environ: {**environ, "PATH": "fresh"}
        )


def offered(
    tools: list,
    saved: Execucao | None,
    *,
    automatic: bool,  # type: ignore[type-arg]
) -> tuple[Mapping[str, str], Said]:
    said = Said()
    result = asyncio.run(
        door._install_offered(tools, saved, Perfil(), said, {"PATH": "old"}, automatic=automatic)
    )
    return result, said


def test_a_person_who_confirmed_gets_the_tools_installed(
    monkeypatch: pytest.MonkeyPatch, environ: dict[str, str], manifest: Manifest
) -> None:
    offer = Offer(monkeypatch)
    environment, _ = offered(missing_tools(environ, manifest), None, automatic=False)
    assert offer.installed == ["tool"]
    assert environment == {"PATH": "fresh"}


def test_nothing_missing_installs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    offer = Offer(monkeypatch)
    environment, said = offered([], None, automatic=False)
    assert offer.installed == []
    assert environment == {"PATH": "old"}
    assert said.lines == []


def test_without_a_terminal_it_installs_only_when_the_execucao_asks(
    monkeypatch: pytest.MonkeyPatch, environ: dict[str, str], manifest: Manifest
) -> None:
    offer = Offer(monkeypatch)
    tools = missing_tools(environ, manifest)
    environment, said = offered(tools, Execucao(), automatic=True)
    assert offer.installed == []
    assert environment == {"PATH": "old"}
    assert "instalar_ferramentas = true" in said.text
    offered(tools, None, automatic=True)
    assert offer.installed == []
    environment, said = offered(tools, Execucao(instalar_ferramentas=True), automatic=True)
    assert offer.installed == ["tool"]
    assert environment == {"PATH": "fresh"}
    assert said.lines == []


def test_a_failed_installation_stops_before_the_run_starts(
    monkeypatch: pytest.MonkeyPatch, environ: dict[str, str], manifest: Manifest
) -> None:
    Offer(monkeypatch, code=1)
    with pytest.raises(Refused, match="instalação das ferramentas falhou"):
        offered(missing_tools(environ, manifest), None, automatic=False)


def test_the_execucao_does_not_install_by_default() -> None:
    assert Execucao().instalar_ferramentas is False
