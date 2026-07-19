from __future__ import annotations

import json
from pathlib import Path

import pytest

from imperaos.artifacts.commands import (
    CreateArtifactCommand,
    MutateArtifactCommand,
    SubmitArtifactFormCommand,
)
from imperaos.artifacts.errors import ArtifactDomainError
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactMutationType,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService


def _document(text: str) -> dict[str, object]:
    return {
        "kind": "document",
        "schemaVersion": 1,
        "language": "tr",
        "pageMode": "document",
        "blocks": [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _context(*, principal_type: PrincipalType, roles: tuple[str, ...]) -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=principal_type,
        principal_id="principal-secret-id",
        roles=roles,
        request_id="request-1",
    )


def test_service_records_hash_bound_redacted_success_and_denial_events(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    editor = _context(principal_type=PrincipalType.USER, roles=("artifact_editor",))
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind=ArtifactKind.DOCUMENT,
            title="Evidence safety",
            data_class=ArtifactDataClass.CONFIDENTIAL,
            content=_document("raw-content-marker"),
            idempotency_key="create-1",
        ),
        editor,
    )

    viewer = _context(principal_type=PrincipalType.USER, roles=("artifact_viewer",))
    with pytest.raises(ArtifactDomainError):
        service.mutate(
            MutateArtifactCommand(
                artifact_id="artifact-1",
                expected_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=_document("denied-content-marker"),
                idempotency_key="denied-1",
            ),
            viewer,
        )

    snapshot = service.evidence.support_bundle_snapshot("workspace-1")
    serialized = json.dumps(snapshot, sort_keys=True)

    assert snapshot["schemaVersion"] == "artifact-evidence-support/v1"
    assert snapshot["chainVerified"] is True
    assert [event["status"] for event in snapshot["events"]] == ["success", "denied"]
    assert snapshot["events"][0]["contentSha256"] == created.revision.content_sha256
    assert snapshot["events"][1]["reasonCode"] == "ARTIFACT_PERMISSION_DENIED"
    assert "raw-content-marker" not in serialized
    assert "denied-content-marker" not in serialized
    assert "principal-secret-id" not in serialized
    assert str(tmp_path) not in serialized


def test_evidence_chain_verification_detects_tampering(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    editor = _context(principal_type=PrincipalType.USER, roles=("artifact_editor",))
    service.create(
        CreateArtifactCommand(
            artifact_id="artifact-1",
            kind=ArtifactKind.DOCUMENT,
            title="Evidence safety",
            data_class=ArtifactDataClass.INTERNAL,
            content=_document("safe"),
            idempotency_key="create-1",
        ),
        editor,
    )

    with service.store._connect() as connection:
        connection.execute(
            "UPDATE artifact_evidence_events SET reason_code = 'TAMPERED' WHERE event_sequence = 1"
        )
        connection.commit()

    assert service.evidence.verify_chain("workspace-1") is False


def test_form_submission_evidence_binds_response_hash_without_raw_values(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    context = _context(principal_type=PrincipalType.USER, roles=("artifact_admin",))
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-form-evidence",
            kind=ArtifactKind.FORM,
            title="Evidence form",
            data_class=ArtifactDataClass.CONFIDENTIAL,
            content={
                "kind": "form",
                "schemaVersion": 1,
                "schema": {
                    "type": "object",
                    "properties": {"secret": {"type": "string"}},
                    "required": ["secret"],
                    "additionalProperties": False,
                },
                "sensitivePaths": ["/secret"],
            },
            idempotency_key="create-form-evidence",
        ),
        context,
    )
    canary = "private-form-evidence-canary"
    submitted = service.submit_form(
        SubmitArtifactFormCommand(
            artifact_id=created.artifact.artifact_id,
            schema_revision_id=created.revision.revision_id,
            response={"secret": canary},
            persistence_policy="none",
            idempotency_key="submit-form-evidence",
        ),
        context,
    )

    snapshot = service.evidence.support_bundle_snapshot("workspace-1")
    submit_event = snapshot["events"][-1]
    assert submit_event["operation"] == "artifact.form.submitted"
    assert submit_event["contentSha256"] == submitted.response_sha256
    assert canary not in json.dumps(snapshot, sort_keys=True)
