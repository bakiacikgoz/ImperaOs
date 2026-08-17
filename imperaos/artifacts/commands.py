from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from imperaos.artifacts.exports import ArtifactExportFormat
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactModel,
    ArtifactMutationType,
    ArtifactStatus,
    BoundedId,
    Sha256,
)


class CreateArtifactCommand(ArtifactModel):
    artifact_id: BoundedId | None = None
    kind: ArtifactKind = Field(strict=False)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    data_class: ArtifactDataClass = Field(strict=False)
    content: dict[str, JsonValue]
    idempotency_key: BoundedId
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class GetArtifactQuery(ArtifactModel):
    artifact_id: BoundedId
    revision_id: BoundedId | None = None


class ListArtifactsQuery(ArtifactModel):
    kind: ArtifactKind | None = Field(default=None, strict=False)
    status: ArtifactStatus | None = Field(default=None, strict=False)
    cursor: Annotated[str | None, StringConstraints(max_length=128, strict=True)] = None
    limit: int = Field(default=50, ge=1, le=200)


class MutateArtifactCommand(ArtifactModel):
    artifact_id: BoundedId
    expected_revision_number: int = Field(ge=1)
    mutation_type: Literal[ArtifactMutationType.REPLACE_CONTENT]
    content: dict[str, JsonValue]
    idempotency_key: BoundedId
    change_summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""


class SpreadsheetSetCellOperation(ArtifactModel):
    op: Literal["set"]
    address: Annotated[str, StringConstraints(min_length=2, max_length=10, strict=True)]
    value: JsonValue


class SpreadsheetClearCellOperation(ArtifactModel):
    op: Literal["clear"]
    address: Annotated[str, StringConstraints(min_length=2, max_length=10, strict=True)]


SpreadsheetCellOperation = Annotated[
    SpreadsheetSetCellOperation | SpreadsheetClearCellOperation,
    Field(discriminator="op"),
]


class PatchSpreadsheetCellsCommand(ArtifactModel):
    artifact_id: BoundedId
    expected_revision_number: int = Field(ge=1)
    sheet_id: BoundedId
    operations: list[SpreadsheetCellOperation] = Field(min_length=1, max_length=10_000)
    idempotency_key: BoundedId
    change_summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""

    @model_validator(mode="after")
    def reject_duplicate_addresses(self) -> PatchSpreadsheetCellsCommand:
        addresses = [operation.address for operation in self.operations]
        if len(addresses) != len(set(addresses)):
            raise ValueError("spreadsheet patch contains duplicate addresses")
        return self


class SlideSetTitleOperation(ArtifactModel):
    op: Literal["set_title"]
    title: Annotated[str | None, StringConstraints(max_length=200, strict=True)] = None


class SlideUpsertElementOperation(ArtifactModel):
    op: Literal["upsert_element"]
    element: dict[str, JsonValue]


class SlideRemoveElementOperation(ArtifactModel):
    op: Literal["remove_element"]
    element_id: BoundedId


SlidePatchOperation = Annotated[
    SlideSetTitleOperation | SlideUpsertElementOperation | SlideRemoveElementOperation,
    Field(discriminator="op"),
]


class PatchArtifactSlideCommand(ArtifactModel):
    artifact_id: BoundedId
    expected_revision_number: int = Field(ge=1)
    slide_id: BoundedId
    operations: list[SlidePatchOperation] = Field(min_length=1, max_length=500)
    idempotency_key: BoundedId
    change_summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""


class ProposeArtifactMutationCommand(ArtifactModel):
    proposal_id: BoundedId | None = None
    artifact_id: BoundedId
    base_revision_number: int = Field(ge=1)
    mutation_type: Literal[ArtifactMutationType.REPLACE_CONTENT]
    content: dict[str, JsonValue]
    idempotency_key: BoundedId
    summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""
    context_sha256: Sha256
    selection_sha256: Sha256
    context_revision_id: BoundedId
    context_purpose: Literal["edit", "transform"]
    target_selection: dict[str, JsonValue]
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None


class ApplyArtifactProposalCommand(ArtifactModel):
    proposal_id: BoundedId
    expected_revision_number: int = Field(ge=1)
    approval_id: BoundedId


class ArtifactHistoryQuery(ArtifactModel):
    artifact_id: BoundedId
    cursor: Annotated[str | None, StringConstraints(max_length=128, strict=True)] = None
    limit: int = Field(default=100, ge=1, le=500)


class RestoreArtifactCommand(ArtifactModel):
    artifact_id: BoundedId
    source_revision_id: BoundedId
    expected_revision_number: int = Field(ge=1)
    idempotency_key: BoundedId
    change_summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""


class ArchiveArtifactCommand(ArtifactModel):
    artifact_id: BoundedId
    expected_revision_number: int = Field(ge=1)


class DuplicateArtifactCommand(ArtifactModel):
    source_artifact_id: BoundedId
    source_revision_id: BoundedId
    artifact_id: BoundedId | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    content_override: dict[str, JsonValue] | None = None
    idempotency_key: BoundedId


class ImportArtifactAssetCommand(ArtifactModel):
    file_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255, strict=True),
    ]
    declared_media_type: Literal[
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    ]
    content_base64: Annotated[
        str,
        StringConstraints(min_length=1, max_length=28_000_000, strict=True),
    ]
    data_class: ArtifactDataClass = Field(strict=False)
    idempotency_key: BoundedId


class GetArtifactAssetQuery(ArtifactModel):
    asset_id: BoundedId


class ImportEvidenceArtifactCommand(ArtifactModel):
    evidence_id: BoundedId
    expected_sha256: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True),
    ]
    artifact_id: BoundedId | None = None
    title: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200, strict=True),
    ] = None
    idempotency_key: BoundedId


class SubmitArtifactFormCommand(ArtifactModel):
    artifact_id: BoundedId
    schema_revision_id: BoundedId
    response: dict[str, JsonValue]
    persistence_policy: Literal["none", "redacted", "encrypted"] = "none"
    idempotency_key: BoundedId


class BeginArtifactExportCommand(ArtifactModel):
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    approval_id: BoundedId | None = None
    idempotency_key: BoundedId


class CommitArtifactExportCommand(ArtifactModel):
    export_id: BoundedId
    basename: Annotated[str, StringConstraints(min_length=1, max_length=255, strict=True)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
    size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    idempotency_key: BoundedId


class PreflightArtifactExportCommand(CommitArtifactExportCommand):
    pass


class CancelArtifactExportCommand(ArtifactModel):
    export_id: BoundedId
    reason: Literal[
        "user_cancelled",
        "serialization_failed",
        "native_write_failed",
        "ticket_expired",
    ]
    idempotency_key: BoundedId
