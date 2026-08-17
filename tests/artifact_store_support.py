from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactMutationType,
    ArtifactRevisionDescriptor,
    ArtifactStatus,
    PrincipalType,
)
from imperaos.artifacts.store import revision_content_relpath


def make_artifact_pair(
    payload: bytes,
    *,
    revision_number: int = 1,
    revision_id: str | None = None,
    parent_revision_id: str | None = None,
    base_revision_id: str | None = None,
    idempotency_key: str | None = None,
    mutation_type: ArtifactMutationType | None = None,
    status: ArtifactStatus = ArtifactStatus.DRAFT,
) -> tuple[ArtifactDescriptor, ArtifactRevisionDescriptor]:
    revision_id = revision_id or f"revision-{revision_number}"
    timestamp = datetime(2026, 7, 16, 8, 0, tzinfo=UTC) + timedelta(minutes=revision_number)
    digest = hashlib.sha256(payload).hexdigest()
    relative_path = revision_content_relpath(
        "workspace-1",
        "artifact-1",
        revision_number,
        revision_id,
        "json",
    )
    revision = ArtifactRevisionDescriptor(
        revision_id=revision_id,
        artifact_id="artifact-1",
        parent_revision_id=parent_revision_id,
        base_revision_id=base_revision_id,
        revision_number=revision_number,
        mutation_type=mutation_type
        or (
            ArtifactMutationType.CREATE
            if revision_number == 1
            else ArtifactMutationType.REPLACE_CONTENT
        ),
        content_relpath=relative_path,
        content_sha256=digest,
        content_size_bytes=len(payload),
        content_encoding="json",
        change_summary=f"revision {revision_number}",
        author_type=PrincipalType.USER,
        author_id="user-1",
        idempotency_key=idempotency_key or f"request-{revision_number}",
        created_at_utc=timestamp,
    )
    artifact = ArtifactDescriptor(
        artifact_id="artifact-1",
        workspace_id="workspace-1",
        kind=ArtifactKind.DOCUMENT,
        title="Quarterly plan",
        status=status,
        schema_version=1,
        data_class=ArtifactDataClass.INTERNAL,
        current_revision_id=revision_id,
        current_revision_number=revision_number,
        source_session_id="session-1",
        source_turn_id="turn-1",
        created_by_type=PrincipalType.USER,
        created_by_id="user-1",
        updated_by_id="user-1",
        created_at_utc=datetime(2026, 7, 16, 8, 0, tzinfo=UTC),
        updated_at_utc=timestamp,
        etag=f"etag-{revision_number}",
        metadata={"department": "operations"},
    )
    return artifact, revision
