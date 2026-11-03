import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from forja.toolchain.load import load_manifest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed"),
]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> zipfile.ZipFile:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "-o", str(out)], cwd=ROOT, check=True, capture_output=True
    )
    (built,) = out.glob("forja-*.whl")
    return zipfile.ZipFile(built)


def test_the_wheel_carries_the_tool_manifest_the_installer_reads(wheel: zipfile.ZipFile) -> None:
    packaged = wheel.read("forja/toolchain/manifest.toml")

    assert packaged == (ROOT / "src/forja/toolchain/manifest.toml").read_bytes()
    assert load_manifest().tools


def test_the_wheel_installs_the_forja_command(wheel: zipfile.ZipFile) -> None:
    (entry_points,) = [n for n in wheel.namelist() if n.endswith("entry_points.txt")]

    assert "forja = forja.cli.main:main" in wheel.read(entry_points).decode()
