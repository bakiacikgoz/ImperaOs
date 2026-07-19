from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ArtifactModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


class ArtifactKind(StrEnum):
    DOCUMENT = "document"
    FORM = "form"
    CODE = "code"
    FLOW = "flow"
    SPREADSHEET = "spreadsheet"
    CANVAS = "canvas"
    SLIDES = "slides"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    BLOCKED = "blocked"
    CORRUPT = "corrupt"


class ArtifactDataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    REGULATED = "regulated"


class PrincipalType(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    IMPORT = "import"


class ArtifactMutationType(StrEnum):
    CREATE = "create"
    REPLACE_CONTENT = "replace_content"
    JSON_PATCH = "json_patch"
    TEXT_EDIT = "text_edit"
    CELL_PATCH = "cell_patch"
    SLIDE_PATCH = "slide_patch"
    RESTORE = "restore"
    DUPLICATE = "duplicate"
    IMPORT_EVIDENCE = "import_evidence"


BoundedId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]


ARTIFACT_CONTENT_LIMITS_BYTES: dict[ArtifactKind, int] = {
    ArtifactKind.DOCUMENT: 5 * 1024 * 1024,
    ArtifactKind.FORM: 512 * 1024,
    ArtifactKind.CODE: 5 * 1024 * 1024,
    ArtifactKind.FLOW: 10 * 1024 * 1024,
    ArtifactKind.SPREADSHEET: 25 * 1024 * 1024,
    ArtifactKind.CANVAS: 25 * 1024 * 1024,
    ArtifactKind.SLIDES: 20 * 1024 * 1024,
}

_DATA_CLASS_RANK = {
    ArtifactDataClass.PUBLIC: 0,
    ArtifactDataClass.INTERNAL: 1,
    ArtifactDataClass.CONFIDENTIAL: 2,
    ArtifactDataClass.REGULATED: 3,
}
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|password|client[_-]?secret|private[_-]?key|credential)",
    re.IGNORECASE,
)
_METADATA_MAX_BYTES = 32 * 1024


def can_transition_data_class(current: ArtifactDataClass, target: ArtifactDataClass) -> bool:
    return _DATA_CLASS_RANK[target] >= _DATA_CLASS_RANK[current]


def canonical_json(model_or_value: BaseModel | dict[str, Any]) -> str:
    value = (
        model_or_value.model_dump(mode="json", by_alias=True)
        if isinstance(model_or_value, BaseModel)
        else model_or_value
    )
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _assert_metadata_safe(value: JsonValue, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_KEY.search(key):
                location = ".".join((*path, key))
                raise ValueError(f"metadata contains secret-shaped key: {location}")
            _assert_metadata_safe(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_metadata_safe(item, (*path, str(index)))


class OperationContext(ArtifactModel):
    workspace_id: BoundedId
    principal_type: PrincipalType = Field(strict=False)
    principal_id: BoundedId
    roles: tuple[BoundedId, ...] = Field(default_factory=tuple, max_length=64)
    request_id: BoundedId
    trace_id: BoundedId | None = None


class ArtifactDescriptor(ArtifactModel):
    artifact_id: BoundedId
    workspace_id: BoundedId
    kind: ArtifactKind = Field(strict=False)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT, strict=False)
    schema_version: int = Field(default=1, ge=1, le=1000)
    data_class: ArtifactDataClass = Field(strict=False)
    current_revision_id: BoundedId
    current_revision_number: int = Field(ge=1)
    source_session_id: BoundedId | None = None
    source_turn_id: BoundedId | None = None
    created_by_type: PrincipalType = Field(strict=False)
    created_by_id: BoundedId
    updated_by_id: BoundedId
    created_at_utc: datetime
    updated_at_utc: datetime
    archived_at_utc: datetime | None = None
    etag: Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("created_at_utc", "updated_at_utc", "archived_at_utc")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _normalize_utc(value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _assert_metadata_safe(value)
        if len(canonical_json(value).encode("utf-8")) > _METADATA_MAX_BYTES:
            raise ValueError(f"metadata exceeds {_METADATA_MAX_BYTES} bytes")
        return value

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ArtifactDescriptor:
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("updatedAtUtc cannot precede createdAtUtc")
        if self.status is ArtifactStatus.ARCHIVED and self.archived_at_utc is None:
            raise ValueError("archived artifacts require archivedAtUtc")
        if self.archived_at_utc is not None and self.archived_at_utc < self.created_at_utc:
            raise ValueError("archivedAtUtc cannot precede createdAtUtc")
        return self


class ArtifactRevisionDescriptor(ArtifactModel):
    revision_id: BoundedId
    artifact_id: BoundedId
    parent_revision_id: BoundedId | None = None
    base_revision_id: BoundedId | None = None
    revision_number: int = Field(ge=1)
    schema_version: int = Field(default=1, ge=1, le=1000)
    mutation_type: ArtifactMutationType = Field(strict=False)
    content_relpath: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    content_sha256: Sha256
    content_size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    content_encoding: Literal["utf-8", "json", "binary"]
    change_summary: Annotated[str, StringConstraints(max_length=500, strict=True)] = ""
    author_type: PrincipalType = Field(strict=False)
    author_id: BoundedId
    idempotency_key: BoundedId
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @field_validator("content_relpath")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith(("/", "~")) or ":" in normalized:
            raise ValueError("contentRelpath must be relative")
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("contentRelpath contains an unsafe segment")
        return normalized


class ArtifactAssetDescriptor(ArtifactModel):
    asset_id: BoundedId
    workspace_id: BoundedId
    sha256: Sha256
    media_type: Literal["image/png", "image/jpeg", "image/gif", "image/webp"]
    size_bytes: int = Field(ge=1, le=20 * 1024 * 1024)
    relative_path: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    width: int | None = Field(default=None, ge=1, le=100_000)
    height: int | None = Field(default=None, ge=1, le=100_000)
    original_name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255, strict=True),
    ] = None
    data_class: ArtifactDataClass = Field(strict=False)
    created_by_id: BoundedId
    created_at_utc: datetime

    @field_validator("created_at_utc")
    @classmethod
    def validate_asset_created_at(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @field_validator("relative_path")
    @classmethod
    def validate_asset_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith(("/", "~")) or ":" in normalized:
            raise ValueError("relativePath must be relative")
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("relativePath contains an unsafe segment")
        return normalized

    @field_validator("original_name")
    @classmethod
    def validate_original_name(cls, value: str | None) -> str | None:
        if value is not None and any(character in value for character in ("/", "\\", "\x00")):
            raise ValueError("originalName must be a basename")
        return value
