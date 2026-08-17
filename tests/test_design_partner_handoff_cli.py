from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_release_train_manifest_cli_outputs_manifest(tmp_path: Path) -> None:
    output = tmp_path / "artifacts" / "design-partner-handoff" / "release_train_manifest.json"
    result = runner.invoke(
        app,
        [
            "release",
            "train",
            "manifest",
            "--profile",
            "enterprise",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.release-train-manifest/v1"
    assert output.exists()


def test_pilot_ops_drill_cli_reports_conditional_deterministic(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "pilot",
            "ops",
            "drill",
            "--profile",
            "enterprise",
            "--output-root",
            str(tmp_path / "artifacts" / "design-partner-handoff"),
        ],
    )

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.pilot-ops-drill/v1"
    assert payload["status"] == "conditional"


def test_release_handoff_verify_missing_manifest_blocks() -> None:
    result = runner.invoke(
        app,
        [
            "release",
            "handoff",
            "verify",
            "--manifest",
            "missing-handoff-manifest.json",
        ],
    )

    assert result.exit_code == 4
    assert json.loads(result.stdout)["blockers"] == ["MANIFEST_MISSING"]
