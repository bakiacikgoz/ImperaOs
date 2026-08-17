from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from imperaos.artifacts.content import ArtifactContent, CodeContentV1, CodeContentV2
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactModel,
    BoundedId,
    Sha256,
)

ArtifactExportFormat = Literal[
    "source",
    "txt",
    "json",
    "submission-json",
    "markdown",
    "html",
    "svg",
    "png",
    "csv",
    "xlsx",
    "pptx",
]
ArtifactExportStatus = Literal["pending", "completed", "cancelled", "failed"]
DEFAULT_ARTIFACT_EXPORT_MAX_BYTES = 100 * 1024 * 1024

ALLOWED_EXPORT_FORMATS: dict[ArtifactKind, frozenset[str]] = {
    ArtifactKind.DOCUMENT: frozenset({"json", "markdown", "html"}),
    ArtifactKind.CODE: frozenset({"source", "txt"}),
    ArtifactKind.FLOW: frozenset({"json", "svg", "png"}),
    ArtifactKind.SPREADSHEET: frozenset({"csv", "xlsx"}),
    ArtifactKind.CANVAS: frozenset({"json", "svg", "png"}),
    ArtifactKind.SLIDES: frozenset({"json", "pptx"}),
    ArtifactKind.FORM: frozenset({"json", "submission-json", "csv"}),
}


class ArtifactExportRecord(ArtifactModel):
    export_id: BoundedId
    workspace_id: BoundedId
    artifact_id: BoundedId
    revision_id: BoundedId
    format: ArtifactExportFormat
    status: ArtifactExportStatus
    basename: str = Field(min_length=1, max_length=255)
    sha256: Sha256 | None = None
    size_bytes: int | None = Field(default=None, ge=0, le=DEFAULT_ARTIFACT_EXPORT_MAX_BYTES)
    actor_type: str
    actor_id: BoundedId
    reason_code: str | None = Field(default=None, max_length=128)


def require_export_format(kind: ArtifactKind, format_name: str) -> str:
    if format_name not in ALLOWED_EXPORT_FORMATS[kind]:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_EXPORT_FAILED,
            "artifact export format is not allowed for this kind",
            details={"kind": kind.value, "format": format_name},
        )
    return format_name


def canonical_export_basename(
    artifact: ArtifactDescriptor,
    content: ArtifactContent,
    format_name: str,
) -> str:
    require_export_format(artifact.kind, format_name)
    if artifact.kind is ArtifactKind.CODE and format_name == "source":
        if not isinstance(content, (CodeContentV1, CodeContentV2)):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "stored code content has an invalid type",
            )
        return content.filename
    extension = {
        "txt": "txt",
        "json": "json",
        "submission-json": "submission.json",
        "markdown": "md",
        "html": "html",
        "svg": "svg",
        "png": "png", "csv": "csv", "xlsx": "xlsx", "pptx": "pptx",
    }[format_name]
    base = re.sub(r"[^\w .-]+", "_", artifact.title, flags=re.UNICODE).strip(" .")[:120]
    if not base or base.upper() in {"CON", "PRN", "AUX", "NUL"}:
        base = "artifact"
    return f"{base}.{extension}"
