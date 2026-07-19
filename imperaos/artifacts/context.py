from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from imperaos.artifacts.commands import GetArtifactQuery
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactModel,
    BoundedId,
    OperationContext,
    Sha256,
)

MAX_CONTEXT_BYTES = 32 * 1024
MAX_CONTEXT_TOKENS = 8_192
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|password|client[_-]?secret|private[_-]?key|secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|credential)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\bsk-[A-Za-z0-9_-]{8,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    r"|\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
    r")",
    re.IGNORECASE,
)
_CELL_RANGE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})(?::([A-Z]{1,3})([1-9][0-9]{0,6}))?$")


class ArtifactContextPurpose(StrEnum):
    EDIT = "edit"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    TRANSFORM = "transform"


class DocumentArtifactSelection(ArtifactModel):
    kind: Literal["document"] = "document"
    block_ids: tuple[BoundedId, ...] = Field(min_length=1, max_length=100, strict=False)


class FormArtifactSelection(ArtifactModel):
    kind: Literal["form"] = "form"
    field_paths: tuple[
        Annotated[str, StringConstraints(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")],
        ...,
    ] = Field(min_length=1, max_length=100, strict=False)


class CodeArtifactSelection(ArtifactModel):
    kind: Literal["code"] = "code"
    start_line_number: int = Field(ge=1, le=5_000_000)
    start_column: int = Field(ge=1, le=1_000_000)
    end_line_number: int = Field(ge=1, le=5_000_000)
    end_column: int = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_order(self) -> CodeArtifactSelection:
        if (self.end_line_number, self.end_column) < (
            self.start_line_number,
            self.start_column,
        ):
            raise ValueError("code selection end precedes start")
        return self


class FlowArtifactSelection(ArtifactModel):
    kind: Literal["flow"] = "flow"
    node_ids: tuple[BoundedId, ...] = Field(default_factory=tuple, max_length=500, strict=False)
    edge_ids: tuple[BoundedId, ...] = Field(default_factory=tuple, max_length=1_000, strict=False)

    @model_validator(mode="after")
    def validate_non_empty(self) -> FlowArtifactSelection:
        if not self.node_ids and not self.edge_ids:
            raise ValueError("flow selection is empty")
        return self


class SpreadsheetArtifactSelection(ArtifactModel):
    kind: Literal["spreadsheet"] = "spreadsheet"
    sheet_id: BoundedId
    ranges: tuple[Annotated[str, StringConstraints(pattern=_CELL_RANGE.pattern)], ...] = Field(
        min_length=1,
        max_length=100,
        strict=False,
    )

    @model_validator(mode="after")
    def validate_bounds(self) -> SpreadsheetArtifactSelection:
        if any(not _valid_cell_range(value) for value in self.ranges):
            raise ValueError("spreadsheet selection exceeds XFD1048576")
        return self


class CanvasArtifactSelection(ArtifactModel):
    kind: Literal["canvas"] = "canvas"
    object_ids: tuple[BoundedId, ...] = Field(min_length=1, max_length=500, strict=False)


class SlidesArtifactSelection(ArtifactModel):
    kind: Literal["slides"] = "slides"
    slide_id: BoundedId
    element_id: BoundedId | None = None


ArtifactContextSelection = Annotated[
    DocumentArtifactSelection
    | FormArtifactSelection
    | CodeArtifactSelection
    | FlowArtifactSelection
    | SpreadsheetArtifactSelection
    | CanvasArtifactSelection
    | SlidesArtifactSelection,
    Field(discriminator="kind"),
]


class ArtifactContextRequest(ArtifactModel):
    artifact_id: BoundedId
    revision_id: BoundedId
    purpose: ArtifactContextPurpose = Field(strict=False)
    allowed_scopes: tuple[Literal["metadata", "selection"], ...] = Field(
        default=("metadata", "selection"), min_length=1, max_length=2, strict=False
    )
    selection: ArtifactContextSelection | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> ArtifactContextRequest:
        if self.selection is not None and "selection" not in self.allowed_scopes:
            raise ValueError("artifact selection scope was not allowed")
        return self


class ArtifactContextPack(ArtifactModel):
    contract_version: Literal["artifact-context-pack/v1"] = "artifact-context-pack/v1"
    artifact_id: BoundedId
    revision_id: BoundedId
    revision_number: int = Field(ge=1)
    kind: ArtifactKind = Field(strict=False)
    schema_version: int = Field(ge=1, le=1_000)
    data_class: ArtifactDataClass = Field(strict=False)
    purpose: ArtifactContextPurpose = Field(strict=False)
    allowed_scopes: tuple[Literal["metadata", "selection"], ...]
    selection: ArtifactContextSelection | None
    projection: dict[str, JsonValue]
    canonical_projection: str
    projection_sha256: Sha256
    selection_sha256: Sha256
    content_sha256: Sha256
    projection_size_bytes: int = Field(ge=2, le=MAX_CONTEXT_BYTES)
    estimated_tokens: int = Field(ge=1, le=MAX_CONTEXT_TOKENS)
    redaction_count: int = Field(ge=0)
    truncated: bool
    reason_code: Literal["ARTIFACT_CONTEXT_READY"] = "ARTIFACT_CONTEXT_READY"


def get_artifact_context(
    service: Any,
    request: ArtifactContextRequest,
    operation_context: OperationContext,
) -> ArtifactContextPack:
    read_result = service.get(
        GetArtifactQuery(
            artifact_id=request.artifact_id,
            revision_id=request.revision_id,
        ),
        operation_context,
    )
    return build_artifact_context_pack(read_result, request)


def build_artifact_context_pack(
    read_result: Any,
    request: ArtifactContextRequest,
) -> ArtifactContextPack:
    artifact = read_result.artifact
    revision = read_result.revision
    if artifact.artifact_id != request.artifact_id or revision.revision_id != request.revision_id:
        _invalid("artifact context identity does not match the authorized revision")
    if request.selection is not None and request.selection.kind != artifact.kind.value:
        _invalid("artifact context selection kind does not match the artifact")

    content = read_result.content.model_dump(mode="json", by_alias=True)
    projection = _project_content(artifact, content, request.selection)
    projection, redaction_count = _redact(projection)
    fitted, truncated = _fit_projection(projection)
    canonical = _canonical(fitted)
    selection_json = _canonical(
        request.selection.model_dump(mode="json", by_alias=True)
        if request.selection is not None
        else None
    )
    size_bytes = len(canonical.encode("utf-8"))
    return ArtifactContextPack(
        artifact_id=artifact.artifact_id,
        revision_id=revision.revision_id,
        revision_number=revision.revision_number,
        kind=artifact.kind,
        schema_version=artifact.schema_version,
        data_class=artifact.data_class,
        purpose=request.purpose,
        allowed_scopes=request.allowed_scopes,
        selection=request.selection,
        projection=fitted,
        canonical_projection=canonical,
        projection_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        selection_sha256=hashlib.sha256(selection_json.encode("utf-8")).hexdigest(),
        content_sha256=revision.content_sha256,
        projection_size_bytes=size_bytes,
        estimated_tokens=max(1, math.ceil(size_bytes / 4)),
        redaction_count=redaction_count,
        truncated=truncated,
    )


def _project_content(
    artifact: Any,
    content: dict[str, JsonValue],
    selection: Any,
) -> dict[str, JsonValue]:
    if selection is None:
        status = getattr(artifact.status, "value", artifact.status)
        return {
            "dataClass": artifact.data_class.value,
            "kind": artifact.kind.value,
            "schemaVersion": artifact.schema_version,
            "status": status,
            "title": artifact.title,
        }
    if selection.kind == "document":
        return {
            "blocks": _select_by_ids(content.get("blocks"), "id", selection.block_ids),
            "language": content.get("language"),
        }
    if selection.kind == "form":
        schema = content.get("schema")
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        selected: dict[str, JsonValue] = {}
        for path in selection.field_paths:
            parts = [
                part.replace("~1", "/").replace("~0", "~")
                for part in path.removeprefix("/").split("/")
            ]
            branch = _project_form_field(properties, parts)
            _merge_form_projection(selected, branch)
        return {"fields": selected}
    if selection.kind == "code":
        lines = str(content.get("text", "")).splitlines(keepends=True)
        if selection.start_line_number > len(lines) or selection.end_line_number > len(lines):
            _invalid("code selection exceeds the current revision")
        selected_lines = lines[selection.start_line_number - 1 : selection.end_line_number]
        if selected_lines:
            selected_lines[0] = selected_lines[0][selection.start_column - 1 :]
            if len(selected_lines) == 1:
                width = selection.end_column - selection.start_column
                selected_lines[0] = selected_lines[0][: max(0, width)]
            else:
                selected_lines[-1] = selected_lines[-1][: selection.end_column - 1]
        return {
            "filename": content.get("filename"),
            "language": content.get("language"),
            "lineEnding": content.get("lineEnding"),
            "range": {
                "startLineNumber": selection.start_line_number,
                "startColumn": selection.start_column,
                "endLineNumber": selection.end_line_number,
                "endColumn": selection.end_column,
            },
            "text": "".join(selected_lines),
        }
    if selection.kind == "flow":
        return {
            "nodes": _select_by_ids(content.get("nodes"), "id", selection.node_ids),
            "edges": _select_by_ids(content.get("edges"), "id", selection.edge_ids),
        }
    if selection.kind == "spreadsheet":
        sheets = content.get("sheets")
        sheet = next(
            (
                item
                for item in sheets
                if isinstance(item, dict) and item.get("id") == selection.sheet_id
            ),
            None,
        ) if isinstance(sheets, list) else None
        if sheet is None:
            _invalid("spreadsheet selection references an unknown sheet")
        cells = sheet.get("cells", {})
        selected_cells = {
            address: value
            for address, value in cells.items()
            if any(_address_in_range(address, cell_range) for cell_range in selection.ranges)
        } if isinstance(cells, dict) else {}
        return {
            "sheetId": selection.sheet_id,
            "ranges": list(selection.ranges),
            "cells": selected_cells,
        }
    if selection.kind == "canvas":
        snapshot = content.get("snapshot")
        objects = snapshot.get("objects", []) if isinstance(snapshot, dict) else []
        return {"objects": _select_by_ids(objects, "id", selection.object_ids)}
    if selection.kind == "slides":
        slides = content.get("slides")
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("id") == selection.slide_id
            ),
            None,
        ) if isinstance(slides, list) else None
        if slide is None:
            _invalid("slides selection references an unknown slide")
        if selection.element_id is None:
            return {"slide": slide}
        elements = slide.get("elements", [])
        selected = _select_by_ids(elements, "id", (selection.element_id,))
        return {"slideId": selection.slide_id, "elements": selected}
    _invalid("artifact context selection kind is unsupported")


def _select_by_ids(
    value: JsonValue,
    key: str,
    selected_ids: tuple[str, ...],
) -> list[dict[str, JsonValue]]:
    items = value if isinstance(value, list) else []
    wanted = set(selected_ids)
    selected = [item for item in items if isinstance(item, dict) and item.get(key) in wanted]
    if len({str(item.get(key)) for item in selected}) != len(wanted):
        _invalid("artifact context selection references an unknown item")
    return selected


def _project_form_field(
    properties: dict[str, JsonValue],
    parts: list[str],
) -> dict[str, JsonValue]:
    if not parts or parts[0] not in properties:
        _invalid("form selection references an unknown field")
    name = parts[0]
    field = properties[name]
    if len(parts) == 1:
        return {name: deepcopy(field)}
    if (
        not isinstance(field, dict)
        or field.get("type") != "object"
        or not isinstance(field.get("properties"), dict)
    ):
        _invalid("form selection traverses a non-object field")
    nested = _project_form_field(field["properties"], parts[1:])
    selected_names = set(nested)
    parent: dict[str, JsonValue] = {
        key: deepcopy(value)
        for key, value in field.items()
        if key != "properties" and not isinstance(value, (dict, list))
    }
    required = field.get("required")
    if isinstance(required, list):
        selected_required = [item for item in required if item in selected_names]
        if selected_required:
            parent["required"] = selected_required
    parent["properties"] = nested
    return {name: parent}


def _merge_form_projection(
    target: dict[str, JsonValue],
    source: dict[str, JsonValue],
) -> None:
    for key, value in source.items():
        if key not in target:
            target[key] = value
            continue
        existing = target[key]
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_form_projection(existing, value)
        elif (
            key == "required"
            and isinstance(existing, list)
            and isinstance(value, list)
            and all(isinstance(item, str) for item in (*existing, *value))
        ):
            existing.extend(item for item in value if item not in existing)
        elif existing != value:
            _invalid("form selection projection is inconsistent")


def _redact(value: JsonValue) -> tuple[JsonValue, int]:
    count = 0

    def visit(item: JsonValue, key: str | None = None) -> JsonValue:
        nonlocal count
        if key is not None and _SECRET_KEY.search(key):
            count += 1
            return "[REDACTED]"
        if isinstance(item, str) and _SECRET_VALUE.search(item):
            count += 1
            return "[REDACTED]"
        if isinstance(item, dict):
            return {name: visit(child, name) for name, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        return item

    return visit(value), count


def _fit_projection(value: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], bool]:
    if len(_canonical(value).encode("utf-8")) <= MAX_CONTEXT_BYTES:
        return value, False
    text = value.get("text")
    if isinstance(text, str):
        low, high = 0, len(text)
        best: dict[str, JsonValue] = {**value, "text": "", "textTruncated": True}
        while low <= high:
            middle = (low + high) // 2
            candidate = {**value, "text": text[:middle], "textTruncated": True}
            if len(_canonical(candidate).encode("utf-8")) <= MAX_CONTEXT_BYTES:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best, True
    return {"summary": "Selected context exceeded the bounded projection budget."}, True


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _column_number(value: str) -> int:
    result = 0
    for character in value:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _range_coordinates(value: str) -> tuple[int, int, int, int] | None:
    match = _CELL_RANGE.fullmatch(value)
    if match is None:
        return None
    start_column, start_row = _column_number(match.group(1)), int(match.group(2))
    end_column = _column_number(match.group(3) or match.group(1))
    end_row = int(match.group(4) or match.group(2))
    return start_column, start_row, end_column, end_row


def _valid_cell_range(value: str) -> bool:
    coordinates = _range_coordinates(value)
    return coordinates is not None and (
        coordinates[0] <= coordinates[2] <= 16_384
        and coordinates[1] <= coordinates[3] <= 1_048_576
    )


def _address_in_range(address: str, cell_range: str) -> bool:
    coordinates = _range_coordinates(address)
    bounds = _range_coordinates(cell_range)
    return bool(
        coordinates
        and bounds
        and bounds[0] <= coordinates[0] <= bounds[2]
        and bounds[1] <= coordinates[1] <= bounds[3]
    )


def _invalid(message: str) -> None:
    raise ArtifactDomainError(ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID, message)
