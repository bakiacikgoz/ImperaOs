from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.artifacts.commands import CreateArtifactCommand
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.cli import app

runner = CliRunner()


def test_artifact_license_doctor_exits_forced_off_with_redacted_json(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "artifact", "license", "doctor", "--kind", "spreadsheet",
            "--profile", "production", "--repo-root", str(tmp_path), "--json",
        ],
    )
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["capability"]["enabled"] is False
    assert payload["capability"]["reasonCode"] == "ARTIFACT_LICENSE_EVIDENCE_MISSING"
    assert "secret" not in result.stdout.lower()
    assert "signature" not in result.stdout.lower()


def _seed(root: Path) -> None:
    service = ArtifactService(root)
    service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind=ArtifactKind.DOCUMENT,
            title="CLI document",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "document",
                "schemaVersion": 1,
                "language": "tr",
                "pageMode": "document",
                "blocks": [],
            },
            idempotency_key="create-1",
        ),
        OperationContext(
            workspace_id="workspace-1",
            principal_type=PrincipalType.USER,
            principal_id="user-1",
            roles=("artifact_admin",),
            request_id="seed-1",
        ),
    )


def test_artifact_cli_doctor_list_get_history_and_integrity(tmp_path: Path) -> None:
    root = tmp_path / "artifact-root"
    _seed(root)

    doctor = runner.invoke(app, ["artifact", "doctor", "--root", str(root)])
    listed = runner.invoke(
        app,
        ["artifact", "list", "--root", str(root), "--workspace", "workspace-1"],
    )
    loaded = runner.invoke(
        app,
        [
            "artifact",
            "get",
            "artifact-1",
            "--root",
            str(root),
            "--workspace",
            "workspace-1",
        ],
    )
    history = runner.invoke(
        app,
        [
            "artifact",
            "history",
            "artifact-1",
            "--root",
            str(root),
            "--workspace",
            "workspace-1",
        ],
    )
    integrity = runner.invoke(
        app,
        [
            "artifact",
            "integrity",
            "verify",
            "--root",
            str(root),
            "--workspace",
            "workspace-1",
        ],
    )

    assert doctor.exit_code == 0, doctor.output
    doctor_payload = json.loads(doctor.output)
    assert doctor_payload["status"] == "ready"
    assert doctor_payload["schemaVersion"] == 12
    assert doctor_payload["integrity"]["status"] == "pass"
    assert len(doctor_payload["metrics"]) == 15
    assert json.loads(listed.output)["count"] == 1
    assert json.loads(loaded.output)["artifact"]["artifactId"] == "artifact-1"
    assert len(json.loads(history.output)["items"]) == 1
    integrity_payload = json.loads(integrity.output)
    assert integrity_payload["artifactCount"] == 1
    assert integrity_payload["revisionCount"] == 1
    assert integrity_payload["verifiedRevisionCount"] == 1
    assert integrity_payload["status"] == "pass"
    assert integrity_payload["workspaceRef"] != "workspace-1"


def test_artifact_cli_migration_plan_is_dry_and_workspace_rpc_is_registered(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifact-root"

    plan = runner.invoke(
        app,
        ["artifact", "migration", "plan", "--root", str(root)],
    )
    rpc_help = runner.invoke(app, ["workspace-rpc", "--help"])

    payload = json.loads(plan.output)
    assert plan.exit_code == 0, plan.output
    assert payload["targetVersion"] == 12
    assert payload["pendingVersions"] == list(range(1, 13))
    assert not root.exists()
    assert rpc_help.exit_code == 0
