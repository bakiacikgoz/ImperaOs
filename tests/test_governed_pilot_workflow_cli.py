from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()
SPEC = "examples/pilot_workflows/enterprise_governed_memory_provider.yaml"


def test_pilot_workflow_cli_validate_passes() -> None:
    result = runner.invoke(app, ["pilot", "workflow", "validate", "--spec", SPEC])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["workflowId"] == "enterprise-governed-memory-provider"


def test_pilot_workflow_cli_run_and_verify(tmp_path: Path) -> None:
    output_root = tmp_path / "governed-pilot-workflow"
    result = runner.invoke(
        app,
        [
            "pilot",
            "workflow",
            "run",
            "--spec",
            SPEC,
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["status"] == "pass"
    assert report["rawPersistence"] is False

    verify = runner.invoke(
        app,
        [
            "pilot",
            "workflow",
            "verify",
            "--report",
            report["reportPath"],
        ],
    )

    assert verify.exit_code == 0
    verification = json.loads(verify.stdout)
    assert verification["status"] == "pass"


def test_control_plane_pilot_workflow_cli_namespace(tmp_path: Path) -> None:
    output_root = tmp_path / "governed-pilot-workflow"
    result = runner.invoke(
        app,
        [
            "control-plane",
            "pilot",
            "workflow",
            "run",
            "--spec",
            SPEC,
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "pass"
