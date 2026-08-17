from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _prepare_enterprise_fixture(root: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "prepare_enterprise_fixture.py"),
            "--root",
            str(root),
            "--permission",
            "workspace.bootstrap",
            "--permission",
            "agent.enrollment.create",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_workspace_bootstrap_blocks_without_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "enterprise",
            "workspace",
            "bootstrap",
            "--profile",
            "enterprise",
            "--organization-id",
            "local-org",
            "--workspace-id",
            "pilot-workspace",
            "--display-name",
            "Pilot Workspace",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["blockingReasons"] == ["IDENTITY_REQUIRED"]
    assert not (tmp_path / ".imperaos" / "control-plane" / "enterprise-workspace").exists()


def test_enterprise_workspace_bootstrap_and_snapshot_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _prepare_enterprise_fixture(tmp_path)

    bootstrap = runner.invoke(
        app,
        [
            "enterprise",
            "workspace",
            "bootstrap",
            "--profile",
            "enterprise",
            "--organization-id",
            "local-org",
            "--workspace-id",
            "pilot-workspace",
            "--display-name",
            "Pilot Workspace",
            "--environment",
            "pilot",
            "--json",
        ],
    )
    snapshot = runner.invoke(
        app,
        ["enterprise", "workspace", "snapshot", "--profile", "enterprise", "--json"],
    )

    assert bootstrap.exit_code == 0, bootstrap.stdout
    bootstrap_payload = json.loads(bootstrap.stdout)
    assert bootstrap_payload["status"] == "created"
    assert bootstrap_payload["rawSecretsExposed"] is False
    assert "alice@example.com" not in bootstrap.stdout
    assert snapshot.exit_code == 0, snapshot.stdout
    snapshot_payload = json.loads(snapshot.stdout)
    assert snapshot_payload["status"] == "ready"
    assert snapshot_payload["networkListenerEnabled"] is False
    assert snapshot_payload["workspaces"][0]["workspaceId"] == "pilot-workspace"
