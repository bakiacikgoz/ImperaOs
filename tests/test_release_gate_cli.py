from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_release_gates_plan_cli_outputs_json() -> None:
    result = runner.invoke(
        app,
        ["release", "gates", "plan", "--target", "mainline-rc", "--profile", "enterprise"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "release.gate-plan/v1"
    assert payload["target"]["targetId"] == "mainline-rc"
    assert "control-plane-gate" in [item["gateId"] for item in payload["gates"]]


def test_release_gates_run_verify_export_cli(tmp_path: Path) -> None:
    output_root = tmp_path / "artifacts" / "release-gates" / "mainline-rc"
    run = runner.invoke(
        app,
        [
            "release",
            "gates",
            "run",
            "--target",
            "mainline-rc",
            "--profile",
            "enterprise",
            "--mode",
            "rc-focused",
            "--output-root",
            str(output_root),
        ],
    )

    assert run.exit_code == 0
    ledger_path = output_root / "gate_evidence_ledger.json"
    assert ledger_path.exists()
    verify = runner.invoke(app, ["release", "gates", "verify", "--ledger", str(ledger_path)])
    assert verify.exit_code == 0
    assert json.loads(verify.stdout)["readyForRcFreeze"] is True
    export = runner.invoke(
        app,
        [
            "release",
            "gates",
            "export",
            "--ledger",
            str(ledger_path),
            "--output-root",
            str(output_root / "export"),
        ],
    )
    assert export.exit_code == 0
    assert (output_root / "export" / "rc_evidence_orchestration_report.json").exists()


def test_control_plane_release_gates_snapshot_cli_reports_missing(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "release",
            "gates",
            "snapshot",
            "--evidence-root",
            str(tmp_path / "artifacts" / "release-gates" / "mainline-rc"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.rc-gate-evidence-snapshot/v1"
    assert payload["status"] == "missing"
