from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from imperaos import __version__
from imperaos.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _entrypoint_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("IMPERAOS_")}
    env.pop("VIRTUAL_ENV", None)
    env["NO_COLOR"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["UV_LINK_MODE"] = "copy"
    return env


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=_entrypoint_env(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def test_editable_console_scripts_use_path_safe_exact_mode() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    sdist = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]
    dependencies = set(project["dependencies"])

    assert project["name"] == "imperaos"
    assert project["version"] == "0.4.1"
    assert project["description"] == "ImperaOS governed AI workforce operating platform"
    assert project["authors"] == [{"name": "ImperaOS Contributors"}]
    assert project["scripts"] == {"imperaos": "imperaos.cli:app"}
    assert wheel["dev-mode-exact"] is True
    assert wheel["packages"] == ["imperaos", "benchmarks", "research", "scripts"]
    assert sdist["include"] == [
        "/imperaos",
        "/benchmarks",
        "/research",
        "/scripts",
        "/config",
        "/branding/identity.json",
        "/hatch_build.py",
        "/pyproject.toml",
        "/README.md",
    ]
    assert "editables>=0.3,<1.0" in dependencies


def test_console_and_module_entrypoints_work_from_current_unicode_path() -> None:
    version_commands = [
        ["uv", "run", "imperaos", "--version"],
        ["uv", "run", "python", "-m", "imperaos", "--version"],
    ]
    for command in version_commands:
        result = _run(command)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == __version__

    capability_commands = [
        ["uv", "run", "imperaos", "operator", "capabilities", "--json"],
        ["uv", "run", "python", "-m", "imperaos", "operator", "capabilities", "--json"],
    ]
    for command in capability_commands:
        result = _run(command)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["contractVersion"] == "3.0"
        assert payload["features"]["computerUseVisionRuntime"]["enabled"] is False


def test_root_help_uses_approved_imperaos_text() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ImperaOS CLI" in result.stdout
    assert "Show ImperaOS version and exit." in result.stdout
