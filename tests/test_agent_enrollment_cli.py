from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _prepare(root: Path) -> None:
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
            "--permission",
            "agent.enrollment.import",
            "--permission",
            "agent.enrollment.approve",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
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
            "--json",
        ],
    )
    assert bootstrap.exit_code == 0, bootstrap.stdout


def test_enterprise_enrollment_cli_token_request_import_approve(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _prepare(tmp_path)

    token_result = runner.invoke(
        app,
        [
            "enterprise",
            "enrollment",
            "token",
            "create",
            "--profile",
            "enterprise",
            "--workspace-id",
            "pilot-workspace",
            "--agent-id",
            "ops-agent",
            "--device-label",
            "ops-host-01",
            "--capability",
            "read",
            "--ttl-minutes",
            "15",
            "--json",
        ],
    )
    token_payload = json.loads(token_result.stdout)
    request_path = tmp_path / "request.json"
    request_result = runner.invoke(
        app,
        [
            "enterprise",
            "enrollment",
            "request",
            "create",
            "--token",
            token_payload["rawToken"],
            "--agent-id",
            "ops-agent",
            "--agent-display-name",
            "Ops Agent",
            "--device-label",
            "ops-host-01",
            "--platform",
            "linux",
            "--capability",
            "read",
            "--output",
            str(request_path),
            "--json",
        ],
    )
    import_result = runner.invoke(
        app,
        [
            "enterprise",
            "enrollment",
            "request",
            "import",
            "--profile",
            "enterprise",
            "--path",
            str(request_path),
            "--json",
        ],
    )
    request_id = json.loads(import_result.stdout)["requestId"]
    approve_result = runner.invoke(
        app,
        [
            "enterprise",
            "enrollment",
            "approve",
            "--profile",
            "enterprise",
            "--request-id",
            request_id,
            "--json",
        ],
    )

    assert token_result.exit_code == 0, token_result.stdout
    assert token_payload["status"] == "created"
    assert token_payload["rawTokenShownOnce"] is True
    assert token_payload["rawTokenPersisted"] is False
    assert request_result.exit_code == 0, request_result.stdout
    assert "rawToken" not in request_path.read_text(encoding="utf-8")
    assert import_result.exit_code == 0, import_result.stdout
    assert approve_result.exit_code == 0, approve_result.stdout
    assert json.loads(approve_result.stdout)["status"] == "approved"
