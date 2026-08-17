from __future__ import annotations

import json
import os
import subprocess
import zipfile
from email.parser import BytesParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PATH = REPO_ROOT / "branding" / "identity.json"


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("wheel")
    env = os.environ.copy()
    env["UV_LINK_MODE"] = "copy"
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(output_dir)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    wheels = list(output_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_wheel_uses_imperaos_distribution_and_package(built_wheel: Path) -> None:
    assert built_wheel.name == "imperaos-0.4.1-py3-none-any.whl"

    with zipfile.ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(wheel.read(metadata_name))

    assert metadata["Name"] == "imperaos"
    assert metadata["Version"] == "0.4.1"
    assert metadata["Summary"] == "ImperaOS governed AI workforce operating platform"
    assert metadata["Author"] == "ImperaOS Contributors"
    assert any(name.startswith("imperaos/") for name in names)
    compatibility_package = "bin" + "liquid"
    assert any(name.startswith(f"{compatibility_package}/") for name in names)


def test_wheel_exposes_only_imperaos_console_script(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        entry_points_name = next(
            name for name in wheel.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = wheel.read(entry_points_name).decode("utf-8")

    assert entry_points.strip().splitlines() == [
        "[console_scripts]",
        "aegis = binliquid.__main__:main",
        "binliquid = binliquid.__main__:main",
        "imperaos = imperaos.cli:app",
    ]


def test_wheel_identity_resource_matches_canonical_source(built_wheel: Path) -> None:
    with zipfile.ZipFile(built_wheel) as wheel:
        packaged_identity = json.loads(wheel.read("imperaos/identity.json"))

    canonical_identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    assert packaged_identity == canonical_identity
