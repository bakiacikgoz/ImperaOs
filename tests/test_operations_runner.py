from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.operations_runner import dry_run_operation
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_operation_dry_run_passes_read_only_identity(tmp_path: Path) -> None:
    result = dry_run_operation(
        config=RuntimeConfig.from_profile("lite"),
        operation_id="auth.whoami",
        actor_id="identity-disabled",
        root_dir=tmp_path / "cp",
        evidence_root=tmp_path / "artifacts",
    )

    assert result.status == "passed"
    assert result.reason_code == "DRY_RUN_PASSED"


def test_operation_dry_run_blocks_destructive_before_permission(tmp_path: Path) -> None:
    result = dry_run_operation(
        config=RuntimeConfig.from_profile("lite"),
        operation_id="migration.apply",
        actor_id="identity-disabled",
        root_dir=tmp_path / "cp",
        evidence_root=tmp_path / "artifacts",
    )

    assert result.status == "blocked"
    assert result.reason_code == "DESTRUCTIVE_OPERATION_DISABLED"


def test_operation_dry_run_blocks_missing_permission(tmp_path: Path) -> None:
    result = dry_run_operation(
        config=RuntimeConfig.from_profile("lite"),
        operation_id="security.baseline",
        actor_id="identity-disabled",
        root_dir=tmp_path / "cp",
        evidence_root=tmp_path / "artifacts",
    )

    assert result.status == "blocked"
    assert result.reason_code == "RBAC_PERMISSION_DENIED"


def test_operation_dry_run_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "operations",
            "dry-run",
            "--profile",
            "lite",
            "--operation-id",
            "auth.whoami",
            "--root-dir",
            str(tmp_path / "cp"),
            "--evidence-root",
            str(tmp_path / "artifacts"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["dryRun"] is True
