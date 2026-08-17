from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from imperaos.artifacts.commands import MutateArtifactCommand, ProposeArtifactMutationCommand
from imperaos.artifacts.errors import ArtifactErrorCode
from imperaos.artifacts.models import (
    ARTIFACT_CONTENT_LIMITS_BYTES,
    ArtifactDataClass,
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactRevisionDescriptor,
    ArtifactStatus,
    OperationContext,
    PrincipalType,
    can_transition_data_class,
    canonical_json,
)


def descriptor_payload() -> dict[str, object]:
    return {
        "artifactId": "artifact-01JTEST",
        "workspaceId": "workspace-main",
        "kind": "document",
        "title": "Quarterly plan",
        "status": "active",
        "schemaVersion": 1,
        "dataClass": "confidential",
        "currentRevisionId": "revision-1",
        "currentRevisionNumber": 1,
        "createdByType": "user",
        "createdById": "operator-1",
        "updatedById": "operator-1",
        "createdAtUtc": datetime(2026, 7, 16, 8, 0, tzinfo=UTC),
        "updatedAtUtc": datetime(2026, 7, 16, 8, 1, tzinfo=UTC),
        "etag": "sha256:metadata",
        "metadata": {"z": 1, "a": {"b": True}},
    }


def test_artifact_descriptor_is_strict_and_serializes_deterministically() -> None:
    first = ArtifactDescriptor.model_validate(descriptor_payload())
    reversed_metadata = descriptor_payload()
    reversed_metadata["metadata"] = {"a": {"b": True}, "z": 1}
    second = ArtifactDescriptor.model_validate(reversed_metadata)

    assert first.kind is ArtifactKind.DOCUMENT
    assert first.status is ArtifactStatus.ACTIVE
    assert first.data_class is ArtifactDataClass.CONFIDENTIAL
    assert canonical_json(first) == canonical_json(second)
    assert '"artifactId":"artifact-01JTEST"' in canonical_json(first)

    invalid_revision = descriptor_payload()
    invalid_revision["currentRevisionNumber"] = "1"
    with pytest.raises(ValidationError):
        ArtifactDescriptor.model_validate(invalid_revision)


def test_artifact_descriptor_normalizes_aware_timestamps_to_utc() -> None:
    payload = descriptor_payload()
    payload["updatedAtUtc"] = datetime(
        2026,
        7,
        16,
        11,
        0,
        tzinfo=timezone(timedelta(hours=3)),
    )

    descriptor = ArtifactDescriptor.model_validate(payload)

    assert descriptor.updated_at_utc == datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("secret_key", ["apiKey", "access_token", "password", "clientSecret"])
def test_artifact_metadata_rejects_secret_shaped_keys(secret_key: str) -> None:
    payload = descriptor_payload()
    payload["metadata"] = {"safe": {secret_key: "must-not-persist"}}

    with pytest.raises(ValidationError, match="secret-shaped"):
        ArtifactDescriptor.model_validate(payload)


def test_artifact_identity_title_and_context_are_bounded() -> None:
    payload = descriptor_payload()
    payload["title"] = " "
    with pytest.raises(ValidationError):
        ArtifactDescriptor.model_validate(payload)

    with pytest.raises(ValidationError):
        OperationContext(
            workspaceId="../escape",
            principalType=PrincipalType.USER,
            principalId="operator-1",
            roles=("artifact.editor",),
            requestId="request-1",
        )


def test_artifact_revision_descriptor_has_hash_and_monotonic_revision() -> None:
    revision = ArtifactRevisionDescriptor(
        revisionId="revision-2",
        artifactId="artifact-01JTEST",
        parentRevisionId="revision-1",
        baseRevisionId="revision-1",
        revisionNumber=2,
        mutationType="replace_content",
        contentRelpath="content/workspace-main/artifact-01JTEST/revisions/2.json",
        contentSha256="a" * 64,
        contentSizeBytes=1024,
        contentEncoding="utf-8",
        changeSummary="Updated summary",
        authorType="user",
        authorId="operator-1",
        idempotencyKey="idem-2",
        createdAtUtc=datetime(2026, 7, 16, 8, 2, tzinfo=UTC),
    )

    assert revision.revision_number == 2
    assert revision.content_sha256 == "a" * 64


def test_data_class_transition_is_monotonic() -> None:
    assert can_transition_data_class(ArtifactDataClass.INTERNAL, ArtifactDataClass.REGULATED)
    assert can_transition_data_class(ArtifactDataClass.CONFIDENTIAL, ArtifactDataClass.CONFIDENTIAL)
    assert not can_transition_data_class(ArtifactDataClass.REGULATED, ArtifactDataClass.PUBLIC)


@pytest.mark.parametrize("command_type", [MutateArtifactCommand, ProposeArtifactMutationCommand])
@pytest.mark.parametrize("reserved_type", ["import_evidence", "slide_patch", "cell_patch"])
def test_general_mutation_contract_rejects_reserved_provenance_and_patch_types(
    command_type: type,
    reserved_type: str,
) -> None:
    payload = {
        "artifactId": "artifact-1",
        "mutationType": reserved_type,
        "content": {"kind": "document", "schemaVersion": 1, "blocks": []},
        "idempotencyKey": "mutation-1",
    }
    if command_type is MutateArtifactCommand:
        payload["expectedRevisionNumber"] = 1
    else:
        payload.update({
            "baseRevisionNumber": 1,
            "contextSha256": "a" * 64,
            "selectionSha256": "b" * 64,
        })

    with pytest.raises(ValidationError):
        command_type.model_validate(payload)


def test_artifact_limits_and_reason_codes_cover_the_plan_contract() -> None:
    assert set(ARTIFACT_CONTENT_LIMITS_BYTES) == set(ArtifactKind)
    assert ARTIFACT_CONTENT_LIMITS_BYTES[ArtifactKind.DOCUMENT] == 5 * 1024 * 1024
    assert ARTIFACT_CONTENT_LIMITS_BYTES[ArtifactKind.FORM] == 512 * 1024
    assert ARTIFACT_CONTENT_LIMITS_BYTES[ArtifactKind.SPREADSHEET] == 25 * 1024 * 1024
    assert {code.value for code in ArtifactErrorCode} == {
        "ARTIFACT_NOT_FOUND",
        "ARTIFACT_KIND_UNSUPPORTED",
        "ARTIFACT_SCHEMA_VERSION_UNSUPPORTED",
        "ARTIFACT_SCHEMA_INVALID",
        "ARTIFACT_CONTENT_TOO_LARGE",
        "ARTIFACT_REVISION_CONFLICT",
        "ARTIFACT_PERMISSION_DENIED",
        "ARTIFACT_POLICY_UNAVAILABLE",
        "ARTIFACT_WORKSPACE_MISMATCH",
        "ARTIFACT_QUOTA_EXCEEDED",
        "ARTIFACT_STORAGE_LOCKED",
        "ARTIFACT_STORAGE_CORRUPT",
        "ARTIFACT_HASH_MISMATCH",
        "ARTIFACT_ASSET_UNSAFE",
        "ARTIFACT_ASSET_TYPE_UNSUPPORTED",
        "ARTIFACT_EXPORT_CANCELLED",
        "ARTIFACT_EXPORT_REQUIRES_CONFIRMATION",
        "ARTIFACT_EXPORT_FAILED",
        "ARTIFACT_RPC_UNAVAILABLE",
        "ARTIFACT_RPC_PROTOCOL_MISMATCH",
        "ARTIFACT_LICENSE_UNAVAILABLE",
        "FORM_SCHEMA_UNSAFE",
        "FORM_VALIDATION_FAILED",
        "FORM_SENSITIVE_PERSISTENCE_DENIED",
        "ASSISTANT_EVENT_SEQUENCE_GAP",
        "ASSISTANT_ARTIFACT_PART_INVALID",
        "IDEMPOTENCY_KEY_REUSE_MISMATCH",
    }
