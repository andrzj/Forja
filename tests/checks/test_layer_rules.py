"""The layer rules check: a new edge to a layer above is rejected; what was there stays."""

import asyncio
from pathlib import Path

from forja.checks.architecture.compare import Snapshot
from forja.checks.layer_rules import NO_LAYERS, LayerRulesCheck
from forja.checks.specs import default_registry
from forja.core.gates import GateInput, InconclusiveReason, Mode
from forja.core.gates.models import Approved, GateResult, Inconclusive, NotApplicable, Rejected
from forja.core.policy import ArchitectureLayer

CLI = ArchitectureLayer("cli", ("cli",))
SERVICE = ArchitectureLayer("service", ("service",))
STORE = ArchitectureLayer("store", ("store",))
LAYERS = (CLI, SERVICE, STORE)  # top to bottom


def tree(**imports: str) -> dict[str, str]:
    """A Python project of one package per name, each importing what the text says."""
    return {f"{name}/__init__.py": text for name, text in imports.items()}


def judge(
    before: dict[str, str],
    after: dict[str, str],
    changed: tuple[str, ...],
    layers: tuple[ArchitectureLayer, ...] = LAYERS,
    base: str = "",
) -> GateResult:
    check = LayerRulesCheck(
        Snapshot("python", before), Snapshot("python", after), changed, layers, base
    )
    data = GateInput(Path("."), "c" * 40, "t", "s", "a")  # type: ignore[arg-type]
    return asyncio.run(check.evaluate(data))


def test_the_check_belongs_to_gate_9_in_observation_and_blocks_when_it_cannot_measure() -> None:
    spec = default_registry().get("layer_rules")

    assert (spec.gate, spec.default_mode, spec.default_on_inconclusive.value) == (
        9,
        Mode.OBSERVATION,
        "block",
    )


def test_without_layers_the_check_does_not_run_and_says_why() -> None:
    result = judge(tree(cli="", store=""), tree(cli="", store="import cli\n"), (), layers=())

    assert result == NotApplicable(missing_capability=NO_LAYERS)
    assert NO_LAYERS == "architecture_layers"


def test_a_new_edge_to_a_layer_above_is_rejected_and_names_both_layers() -> None:
    before = tree(cli="import store\n", store="")
    after = tree(cli="import store\n", store="import cli\n")

    result = judge(before, after, ("store/__init__.py",))

    assert isinstance(result, Rejected)
    (finding,) = result.findings
    assert finding.message == "layer store depends on cli, a layer above it"
    assert finding.target == "store -> cli"


def test_an_edge_to_a_layer_below_or_to_the_same_layer_passes() -> None:
    before = tree(cli="", service="", store="")
    after = tree(
        cli="import service\nimport store\n",
        service="import store\n",
        store="",
    )
    after["service/more.py"] = "import service\n"
    after["service/deep/__init__.py"] = "import service\n"
    paths = ("cli/__init__.py", "service/__init__.py", "service/deep/__init__.py")

    assert isinstance(judge(before, after, paths), Approved)


def test_an_edge_that_already_pointed_up_is_the_pasts_and_passes() -> None:
    both = tree(cli="", service="", store="import cli\n")
    after = {**both, "store/extra.py": "x = 1\n"}

    assert isinstance(judge(both, after, ("store/extra.py",)), Approved)


def test_every_new_edge_up_is_reported_once_and_in_order() -> None:
    before = tree(cli="", service="", store="")
    after = tree(cli="", service="import cli\n", store="import cli\nimport service\n")

    result = judge(before, after, ("service/__init__.py", "store/__init__.py"))

    assert isinstance(result, Rejected)
    assert [f.target for f in result.findings] == [
        "service -> cli",
        "store -> cli",
        "store -> service",
    ]


def test_a_directory_in_no_layer_is_free_on_either_side() -> None:
    before = tree(cli="", util="", store="")
    after = tree(cli="import util\n", util="import cli\nimport store\n", store="import util\n")

    paths = ("cli/__init__.py", "util/__init__.py", "store/__init__.py")
    assert isinstance(judge(before, after, paths), Approved)


def test_a_directory_below_a_layer_path_belongs_to_that_layer() -> None:
    before = tree(cli="", store="")
    before["store/deep/__init__.py"] = ""
    after = {**before, "store/deep/__init__.py": "import cli\n"}

    result = judge(before, after, ("store/deep/__init__.py",))

    assert isinstance(result, Rejected)
    assert result.findings[0].target == "store/deep -> cli"


def test_a_path_that_only_shares_a_prefix_is_not_inside_the_layer() -> None:
    before = tree(cli="", storefront="")
    after = tree(cli="", storefront="import cli\n")
    layers = (CLI, ArchitectureLayer("store", ("store",)))

    assert isinstance(judge(before, after, ("storefront/__init__.py",), layers), Approved)


def test_the_deepest_path_decides_when_layers_nest() -> None:
    wide = ArchitectureLayer("all", ("app",))
    narrow = ArchitectureLayer("domain", ("app/domain",))
    layers = (wide, narrow)  # the rest of app on top of its domain
    before = {"app/__init__.py": "", "app/domain/__init__.py": ""}
    down = {"app/__init__.py": "import app.domain\n", "app/domain/__init__.py": ""}
    up = {"app/__init__.py": "", "app/domain/__init__.py": "import app\n"}

    assert isinstance(judge(before, down, ("app/__init__.py",), layers), Approved)
    result = judge(before, up, ("app/domain/__init__.py",), layers)
    assert isinstance(result, Rejected)
    assert result.findings[0].message == "layer domain depends on all, a layer above it"
    assert result.findings[0].target == "app/domain -> app"


def test_the_layer_paths_are_repository_paths_and_the_project_may_sit_below_the_root() -> None:
    layers = (ArchitectureLayer("cli", ("pkg/cli",)), ArchitectureLayer("store", ("pkg/store",)))
    before = tree(cli="", store="")
    after = tree(cli="", store="import cli\n")

    assert isinstance(judge(before, after, ("store/__init__.py",), layers), Approved)
    result = judge(before, after, ("store/__init__.py",), layers, base="pkg")
    assert isinstance(result, Rejected)
    assert result.findings[0].target == "store -> cli"


def test_the_project_root_belongs_to_a_layer_only_through_its_base() -> None:
    top = ArchitectureLayer("top", ("pkg",))
    low = ArchitectureLayer("low", ("pkg/low",))
    before = {"main.py": "", "low/__init__.py": ""}
    after = {"main.py": "", "low/__init__.py": "import main\n"}

    assert isinstance(judge(before, after, ("low/__init__.py",), (top, low)), Approved)
    result = judge(before, after, ("low/__init__.py",), (top, low), base="pkg")
    assert isinstance(result, Rejected)
    assert result.findings[0].target == "low -> ."


def test_a_parent_commit_with_nothing_to_read_makes_every_edge_new() -> None:
    after = tree(cli="", store="import cli\n")

    result = judge({}, after, ("store/__init__.py",))

    assert isinstance(result, Rejected)


def test_a_change_that_leaves_the_graph_alone_passes() -> None:
    both = tree(cli="", store="import cli\n")

    assert isinstance(judge(both, {**both, "notes.txt": "x"}, ("notes.txt",)), Approved)


def test_a_changed_file_that_does_not_parse_is_inconclusive() -> None:
    before = tree(cli="", store="")
    after = tree(cli="", store="def (:\n")

    result = judge(before, after, ("store/__init__.py",))

    assert isinstance(result, Inconclusive)
    assert result.reason is InconclusiveReason.UNSUPPORTED_CONSTRUCT


def test_a_directory_belongs_to_the_deepest_layer_path_whatever_the_position() -> None:
    layers = (
        ArchitectureLayer("high", ("zz",)),
        ArchitectureLayer("mid", ("yy",)),
        ArchitectureLayer("core", ("src/core",)),
        ArchitectureLayer("all", ("src",)),
    )
    before = {"zz/__init__.py": "", "src/core/z/__init__.py": ""}
    after = {"zz/__init__.py": "", "src/core/z/__init__.py": "import zz\n"}

    result = judge(before, after, ("src/core/z/__init__.py",), layers=layers)

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "layer core depends on high, a layer above it"


def test_two_layers_with_the_same_path_leave_the_directory_to_the_upper_one() -> None:
    layers = (
        ArchitectureLayer("top", ("app",)),
        ArchitectureLayer("first", ("lib",)),
        ArchitectureLayer("second", ("lib",)),
    )
    before = tree(app="", lib="")
    after = tree(app="", lib="import app\n")

    result = judge(before, after, ("lib/__init__.py",), layers=layers)

    assert isinstance(result, Rejected)
    assert result.findings[0].message == "layer first depends on top, a layer above it"
