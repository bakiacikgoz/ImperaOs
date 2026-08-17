from __future__ import annotations

import json
from pathlib import Path

from imperaos.artifacts.commands import CreateArtifactCommand
from imperaos.artifacts.diagnostics import (
    build_artifact_doctor_report,
    build_artifact_support_snapshot,
    verify_artifact_integrity,
)
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService


def _seed(service: ArtifactService) -> None:
    service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind=ArtifactKind.DOCUMENT,
            title="Diagnostic document",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "document",
                "schemaVersion": 1,
                "language": "tr",
                "pageMode": "document",
                "blocks": [],
            },
            idempotency_key="create-diagnostic",
        ),
        OperationContext(
            workspace_id="workspace-1",
            principal_type=PrincipalType.USER,
            principal_id="user-1",
            roles=("artifact_admin",),
            request_id="request-diagnostic",
        ),
    )


def test_integrity_verifies_sqlite_hashes_evidence_and_orphans_without_raw_content(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    _seed(service)

    report = verify_artifact_integrity(service, workspace_id="workspace-1")

    assert report["status"] == "pass"
    assert report["sqliteIntegrity"] == "ok"
    assert report["artifactCount"] == 1
    assert report["revisionCount"] == 1
    assert report["verifiedRevisionCount"] == 1
    assert report["evidenceChainFailureCount"] == 0
    assert report["orphanContentFileCount"] == 0
    assert report["orphanAssetFileCount"] == 0
    assert service.operations.snapshot()["imperaos_artifact_create_total"] == 1
    create_series = next(
        item
        for item in service.operations.series_snapshot()
        if item["name"] == "imperaos_artifact_create_total"
    )
    assert create_series["labels"] == {"kind": "document", "result": "success"}
    assert create_series["value"] == 1
    assert service.operation_logs[-1]["operation"] == "artifact.create"
    assert service.operation_logs[-1]["artifact_kind"] == "document"
    assert "Diagnostic document" not in json.dumps(list(service.operation_logs))
    assert "Diagnostic document" not in json.dumps(report)


def test_doctor_and_support_snapshot_fail_closed_on_tamper_and_are_redacted(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    _seed(service)
    revision = service.store.list_revisions("workspace-1", "artifact-1")[0]
    service.store.filesystem.resolve_relative(revision.content_relpath).write_bytes(b"tampered")

    doctor = build_artifact_doctor_report(service)
    support = build_artifact_support_snapshot(service)

    assert doctor["status"] == "blocked"
    assert doctor["integrity"]["revisionHashMismatchCount"] == 1
    assert support["status"] == "blocked"
    assert support["database"]["integrity"] == "ok"
    assert support["licenses"][0]["enabled"] is False
    serialized = json.dumps(support).lower()
    for forbidden in ("tampered", "diagnostic document", "secretref", "relativepath"):
        assert forbidden not in serialized
