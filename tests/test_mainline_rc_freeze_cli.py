from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_release_mainline_stack_verify_cli_outputs_json(tmp_path: Path) -> None:
    stack = tmp_path / "stack.yaml"
    stack.write_text(
        "\n".join(
            [
                "schemaVersion: control-plane.mainline-stack-spec/v1",
                "stackName: design-partner-rc",
                "baseBranch: main",
                "items:",
                "  - prNumber: 10",
                "    branch: codex/workspace-memory-authority-v1",
                "    baseBranch: main",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["release", "mainline", "stack-verify", "--stack", str(stack)])

    assert result.exit_code in {0, 3}
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.mainline-stack-verification/v1"
    assert payload["stackName"] == "design-partner-rc"


def test_release_mainline_rehearse_cli_dry_run_outputs_json(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "release",
            "mainline",
            "rehearse",
            "--base",
            "main",
            "--head",
            "codex/design-partner-rc-handoff-ops-readiness-v1",
            "--mode",
            "dry-run",
            "--output-root",
            str(tmp_path / "artifacts" / "mainline-rc-freeze"),
        ],
    )

    assert result.exit_code in {0, 4}
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.mainline-merge-rehearsal/v1"
    assert payload["worktreeMutated"] is False


def test_release_rc_freeze_build_and_verify_cli(tmp_path: Path) -> None:
    stack = tmp_path / "stack.yaml"
    stack.write_text(
        "\n".join(
            [
                "schemaVersion: control-plane.mainline-stack-spec/v1",
                "stackName: design-partner-rc",
                "baseBranch: main",
                "items:",
                "  - prNumber: 10",
                "    branch: codex/workspace-memory-authority-v1",
                "    baseBranch: main",
            ]
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "artifacts" / "mainline-rc-freeze"

    build = runner.invoke(
        app,
        [
            "release",
            "rc-freeze",
            "build",
            "--profile",
            "enterprise",
            "--stack",
            str(stack),
            "--evidence-root",
            str(tmp_path / "artifacts"),
            "--output-root",
            str(output_root),
            "--freeze-id",
            "freeze-cli",
        ],
    )

    assert build.exit_code in {0, 3, 4}
    manifest_path = output_root / "manifest.json"
    assert manifest_path.exists()
    verify = runner.invoke(
        app,
        ["release", "rc-freeze", "verify", "--manifest", str(manifest_path)],
    )

    assert verify.exit_code in {0, 3, 4}
    assert json.loads(verify.stdout)["schemaVersion"] == "control-plane.rc-freeze-verification/v1"


def test_release_rc_freeze_export_cli_copies_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"schemaVersion":"control-plane.rc-freeze-manifest/v1"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "exported.json"

    result = runner.invoke(
        app,
        [
            "release",
            "rc-freeze",
            "export",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.exists()


def test_control_plane_release_freeze_snapshot_cli_reports_missing(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "release",
            "freeze",
            "snapshot",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "control-plane.mainline-rc-freeze-snapshot/v1"
    assert payload["status"] == "missing"
