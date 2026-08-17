from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import model_validator

from imperaos.artifacts.content import ArtifactContent
from imperaos.artifacts.exports import ArtifactExportFormat, ArtifactExportStatus
from imperaos.artifacts.models import (
    ArtifactAssetDescriptor,
    ArtifactDescriptor,
    ArtifactModel,
    ArtifactRevisionDescriptor,
    BoundedId,
    Sha256,
)


class ArtifactAssetImportResult(ArtifactModel):
    asset: ArtifactAssetDescriptor
    disposition: Literal["created", "deduplicated", "idempotent_replay"]


class ArtifactAssetReadResult(ArtifactModel):
    asset: ArtifactAssetDescriptor
    content_base64: str


@dataclass(frozen=True, slots=True)
class ArtifactOperationResult:
    artifact: ArtifactDescriptor
    revision: ArtifactRevisionDescriptor
    created: bool
    disposition: Literal["created", "no_op", "idempotent_replay", "updated"]


@dataclass(frozen=True, slots=True)
class ArtifactReadResult:
    artifact: ArtifactDescriptor
    revision: ArtifactRevisionDescriptor
    content: ArtifactContent


@dataclass(frozen=True, slots=True)
class ArtifactListResult:
    items: tuple[ArtifactDescriptor, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactHistoryResult:
    items: tuple[ArtifactRevisionDescriptor, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactMutationProposalResult:
    proposal_id: str
    artifact_id: str
    base_revision_number: int
    status: Literal["pending", "applied", "rejected", "stale"]
    content_sha256: str
    summary: str
    approval_id: str
    action_hash: str


class ArtifactFormSubmissionResult(ArtifactModel):
    submission_id: BoundedId
    artifact_id: BoundedId
    schema_revision_id: BoundedId
    status: Literal["accepted", "pending_continuation"]
    response_sha256: Sha256
    continuation_action: Literal["none", "require_approval"]
    approval_id: BoundedId | None = None
    reason_code: Literal[
        "FORM_CONTINUATION_NOT_REQUIRED",
        "FORM_CONTINUATION_APPROVAL_REQUIRED",
    ]
    action_hash: Sha256 | None = None
    disposition: Literal["created", "idempotent_replay"]

    @model_validator(mode="after")
    def validate_continuation_binding(self) -> ArtifactFormSubmissionResult:
        pending = self.status == "pending_continuation"
        if pending != (self.continuation_action == "require_approval"):
            raise ValueError("form continuation status is inconsistent")
        if pending != (self.approval_id is not None and self.action_hash is not None):
            raise ValueError("form continuation approval binding is inconsistent")
        expected_reason = (
            "FORM_CONTINUATION_APPROVAL_REQUIRED"
            if pending
            else "FORM_CONTINUATION_NOT_REQUIRED"
        )
        if self.reason_code != expected_reason:
            raise ValueError("form continuation reason is inconsistent")
        return self


class ArtifactExportBeginResult(ArtifactModel):
    export_id: BoundedId
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    basename: str
    max_bytes: int
    disposition: Literal["created", "idempotent_replay"]


class ArtifactExportResult(ArtifactModel):
    export_id: BoundedId
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    status: ArtifactExportStatus
    basename: str
    sha256: Sha256 | None = None
    size_bytes: int | None = None
    reason_code: str | None = None
    disposition: Literal["updated", "idempotent_replay"]
