from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Annotated, ClassVar, Literal

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from pydantic import Field, JsonValue, StringConstraints, field_validator, model_validator

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ARTIFACT_CONTENT_LIMITS_BYTES,
    ArtifactKind,
    ArtifactModel,
    BoundedId,
)


class ArtifactContentModel(ArtifactModel):
    schema_version: Literal[1] = 1


def _contains_remote_url(value: JsonValue) -> bool:
    if isinstance(value, str):
        return value.strip().lower().startswith(("http://", "https://", "//"))
    if isinstance(value, dict):
        return any(_contains_remote_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_remote_url(item) for item in value)
    return False


class DocumentContentV1(ArtifactContentModel):
    kind: Literal["document"] = "document"
    language: Annotated[
        str, StringConstraints(min_length=2, max_length=16, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    ]
    page_mode: Literal["document", "paginated"] = "document"
    blocks: list[dict[str, JsonValue]] = Field(max_length=10_000)

    @field_validator("blocks")
    @classmethod
    def reject_remote_content(cls, value: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
        if _contains_remote_url(value):
            raise ValueError("document contains a remote URL")
        return value


_FORM_ALLOWED_KEYS = {
    "$schema",
    "$ref",
    "definitions",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "enum",
    "const",
    "oneOf",
    "items",
    "additionalProperties",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "pattern",
    "format",
    "default",
    "examples",
}
_FORM_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_FORM_FORMATS = {"date", "date-time", "email", "hostname", "ipv4", "ipv6", "uri-reference", "uuid"}
_DRAFT7_SCHEMA_URI = "http://json-schema.org/draft-07/schema#"
_FORM_MAX_FIELDS = 100
_FORM_MAX_DEPTH = 6
_FORM_MAX_BYTES = 512 * 1024
_FORM_FIELD_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FORM_FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}


def _validate_form_schema(schema: dict[str, JsonValue]) -> None:
    if schema.get("type") != "object":
        raise ValueError("form schema root must be an object")
    field_count = 0
    local_refs: set[tuple[str, str]] = set()

    def validate_field_key(value: object) -> str:
        if (
            not isinstance(value, str)
            or value in _FORM_FORBIDDEN_KEYS
            or _FORM_FIELD_KEY.fullmatch(value) is None
        ):
            raise ValueError("form schema contains an unsafe field key")
        return value

    def visit(node: JsonValue, depth: int) -> None:
        nonlocal field_count
        if depth > _FORM_MAX_DEPTH:
            raise ValueError(f"form schema depth exceeds {_FORM_MAX_DEPTH}")
        if not isinstance(node, dict):
            return
        unknown = set(node) - _FORM_ALLOWED_KEYS
        if unknown:
            raise ValueError(f"form schema contains unsupported keys: {sorted(unknown)}")
        raw_ref = node.get("$ref")
        if isinstance(raw_ref, str):
            parts = raw_ref.split("/")
            if len(parts) != 3 or parts[0] != "#" or parts[1] != "definitions":
                raise ValueError("remote refs are forbidden")
            local_refs.add((parts[1], validate_field_key(parts[2])))
        raw_type = node.get("type")
        if "type" in node and (not isinstance(raw_type, str) or raw_type not in _FORM_TYPES):
            raise ValueError("unsupported form type")
        raw_format = node.get("format")
        if "format" in node and (
            not isinstance(raw_format, str) or raw_format not in _FORM_FORMATS
        ):
            raise ValueError("unsupported form format")
        pattern = node.get("pattern")
        if "pattern" in node:
            if not isinstance(pattern, str):
                raise ValueError("invalid pattern in form schema")
            if len(pattern) > 256 or not _is_safe_form_pattern(pattern):
                raise ValueError("unsafe pattern in form schema")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError("invalid pattern in form schema") from error
        one_of = node.get("oneOf")
        if isinstance(one_of, list):
            if len(one_of) > 20:
                raise ValueError("form oneOf exceeds 20 branches")
            for item in one_of:
                visit(item, depth + 1)
        properties = node.get("properties")
        if isinstance(properties, dict):
            for key in properties:
                validate_field_key(key)
            field_count += len(properties)
            if field_count > _FORM_MAX_FIELDS:
                raise ValueError(f"form schema exceeds {_FORM_MAX_FIELDS} fields")
            for child in properties.values():
                visit(child, depth + 1)
        definitions = node.get("definitions")
        if isinstance(definitions, dict):
            for key in definitions:
                validate_field_key(key)
            for child in definitions.values():
                visit(child, depth + 1)
        items = node.get("items")
        if isinstance(items, dict):
            visit(items, depth + 1)
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            raise ValueError("schema-valued additionalProperties is not allowed")

    serialized = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > _FORM_MAX_BYTES:
        raise ValueError(f"form schema exceeds {_FORM_MAX_BYTES} bytes")
    raw_dialect = schema.get("$schema")
    if raw_dialect is not None and raw_dialect != _DRAFT7_SCHEMA_URI:
        raise ValueError("unsupported form schema dialect")
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError("form schema is not valid Draft-07") from error
    visit(schema, 1)
    for definitions_key, definition_name in local_refs:
        definitions = schema.get(definitions_key)
        if not isinstance(definitions, dict) or definition_name not in definitions:
            raise ValueError("form schema contains an unresolved local ref")
    _reject_cyclic_form_refs(schema)


def _is_safe_form_pattern(pattern: str) -> bool:
    outside_classes: list[str] = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            index += 2
            continue
        if character == "[":
            index += 1
            while index < len(pattern) and pattern[index] != "]":
                if pattern[index] == "\\":
                    index += 2
                else:
                    index += 1
            index += 1
            continue
        outside_classes.append(character)
        index += 1
    operators = "".join(outside_classes)
    return (
        not any(character in operators for character in "()|*+")
        and re.search(r"\{\d+,\}", operators) is None
    )


def _reject_cyclic_form_refs(schema: dict[str, JsonValue]) -> None:
    definitions = schema.get("definitions")
    if not isinstance(definitions, dict):
        return

    def references(value: JsonValue) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            raw_ref = value.get("$ref")
            if isinstance(raw_ref, str) and raw_ref.startswith("#/definitions/"):
                found.add(raw_ref.removeprefix("#/definitions/"))
            for child in value.values():
                found.update(references(child))
        elif isinstance(value, list):
            for child in value:
                found.update(references(child))
        return found

    graph = {name: references(value) for name, value in definitions.items()}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_definition(name: str) -> None:
        if name in visiting:
            raise ValueError("form schema contains cyclic local refs")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph.get(name, set()):
            visit_definition(dependency)
        visiting.remove(name)
        visited.add(name)

    for definition_name in graph:
        visit_definition(definition_name)


_UI_KEYS = {"ui:widget", "ui:options", "ui:placeholder", "ui:help", "ui:title", "ui:description"}
_UI_WIDGETS = {"text", "textarea", "select", "checkbox", "radio", "date", "hidden"}
_UI_FORBIDDEN_KEYS = {"src", "url", "href", "html", "dangerouslysetinnerhtml", "script"}


def _validate_ui_schema(value: JsonValue) -> None:
    if isinstance(value, str) and _contains_remote_url(value):
        raise ValueError("uiSchema contains a remote URL")
    if isinstance(value, list):
        for item in value:
            _validate_ui_schema(item)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        lowered = key.lower()
        if key.startswith("ui:") and key not in _UI_KEYS:
            raise ValueError(f"uiSchema contains unsupported directive: {key}")
        if lowered in _UI_FORBIDDEN_KEYS or lowered.startswith("on"):
            raise ValueError(f"uiSchema contains forbidden key: {key}")
        if key == "ui:widget" and item not in _UI_WIDGETS:
            raise ValueError(f"uiSchema contains unsupported widget: {item}")
        _validate_ui_schema(item)


class FormBehavior(ArtifactModel):
    submit_mode: Literal["explicit"] = "explicit"
    external_continuation: Literal["deny", "approval_required"] = "deny"


class FormContentV1(ArtifactContentModel):
    kind: Literal["form"] = "form"
    json_schema: dict[str, JsonValue] = Field(alias="schema")
    ui_schema: dict[str, JsonValue] = Field(default_factory=dict)
    behavior: FormBehavior = Field(default_factory=FormBehavior)
    sensitive_paths: list[
        Annotated[str, StringConstraints(pattern=r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")]
    ] = Field(
        default_factory=list,
        max_length=100,
    )

    @field_validator("json_schema")
    @classmethod
    def validate_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _validate_form_schema(value)
        return value

    @field_validator("ui_schema")
    @classmethod
    def validate_ui_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        _validate_ui_schema(value)
        return value


class CodeContentV1(ArtifactContentModel):
    kind: Literal["code"] = "code"
    filename: Annotated[
        str,
        StringConstraints(min_length=1, max_length=255, pattern=r"^[^/\\:\x00]+$", strict=True),
    ]
    language: Annotated[
        str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z0-9_+-]+$")
    ]
    text: Annotated[str, StringConstraints(max_length=5 * 1024 * 1024, strict=True)]
    line_ending: Literal["lf", "crlf"] = "lf"
    execution_policy: Literal["deny"] = "deny"


class CodeContentV2(ArtifactModel):
    schema_version: Literal[2] = 2
    kind: Literal["code"] = "code"
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255, strict=True)]
    language: Literal[
        "plaintext",
        "bat",
        "c",
        "cpp",
        "csharp",
        "css",
        "go",
        "html",
        "java",
        "javascript",
        "json",
        "markdown",
        "powershell",
        "python",
        "rust",
        "shell",
        "sql",
        "typescript",
        "xml",
        "yaml",
    ]
    text: Annotated[str, StringConstraints(max_length=5 * 1024 * 1024, strict=True)]
    line_ending: Literal["lf", "crlf"] = "lf"
    execution_policy: Literal["deny"] = "deny"

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if value != unicodedata.normalize("NFC", value):
            raise ValueError("code filename must use NFC normalization")
        if value != value.strip() or value in {".", ".."} or value.endswith("."):
            raise ValueError("code filename is not portable")
        if any(character in '<>:"/\\|?*' for character in value):
            raise ValueError("code filename contains a forbidden character")
        if any(
            unicodedata.category(character) in {"Cc", "Cf"}
            or 0x13439 <= ord(character) <= 0x1343F
            for character in value
        ):
            raise ValueError("code filename contains a control character")
        basename = value.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update({f"COM{index}" for index in range(1, 10)})
        reserved.update({f"LPT{index}" for index in range(1, 10)})
        if basename in reserved:
            raise ValueError("code filename uses a reserved device name")
        return value

    @model_validator(mode="after")
    def validate_line_endings(self) -> CodeContentV2:
        if self.line_ending == "lf":
            if "\r" in self.text:
                raise ValueError("code text does not match LF line ending")
        elif re.search(r"(?<!\r)\n|\r(?!\n)", self.text):
            raise ValueError("code text does not match CRLF line ending")
        return self


class FlowPosition(ArtifactModel):
    x: float
    y: float


class FlowNode(ArtifactModel):
    id: BoundedId
    type: Literal["input", "output", "process", "decision", "note", "group", "artifact"]
    position: FlowPosition
    data: dict[str, JsonValue] = Field(default_factory=dict)


class FlowEdge(ArtifactModel):
    id: BoundedId
    source: BoundedId
    target: BoundedId
    label: Annotated[str, StringConstraints(max_length=200, strict=True)] | None = None


class FlowViewport(ArtifactModel):
    x: float
    y: float
    zoom: float = Field(ge=0.05, le=8.0)


class FlowContentV1(ArtifactContentModel):
    kind: Literal["flow"] = "flow"
    nodes: list[FlowNode] = Field(max_length=5_000)
    edges: list[FlowEdge] = Field(max_length=10_000)
    viewport: FlowViewport

    @model_validator(mode="after")
    def validate_graph(self) -> FlowContentV1:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("flow contains duplicate node ids")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("flow contains duplicate edge ids")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"flow edge has unknown source: {edge.source}")
            if edge.target not in known:
                raise ValueError(f"flow edge has unknown target: {edge.target}")
        return self


class FlowPositionV2(ArtifactModel):
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)


class FlowNodeDataV2(ArtifactModel):
    label: Annotated[str, StringConstraints(min_length=1, max_length=200, strict=True)]
    description: Annotated[str, StringConstraints(max_length=1_000, strict=True)] | None = None
    artifact_id: BoundedId | None = None

    @field_validator("label", "description")
    @classmethod
    def reject_control_text(cls, value: str | None) -> str | None:
        if value is not None and any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in value
        ):
            raise ValueError("flow text contains a control character")
        return value


class FlowNodeV2(ArtifactModel):
    id: BoundedId
    type: Literal["input", "output", "process", "decision", "note", "group", "artifact"]
    position: FlowPositionV2
    data: FlowNodeDataV2

    @model_validator(mode="after")
    def validate_artifact_binding(self) -> FlowNodeV2:
        if self.type == "artifact" and self.data.artifact_id is None:
            raise ValueError("artifact flow node requires artifactId")
        if self.type != "artifact" and self.data.artifact_id is not None:
            raise ValueError("artifactId is only valid for artifact flow nodes")
        return self


class FlowEdgeV2(ArtifactModel):
    id: BoundedId
    source: BoundedId
    target: BoundedId
    label: Annotated[str, StringConstraints(max_length=200, strict=True)] | None = None

    @field_validator("label")
    @classmethod
    def reject_control_label(cls, value: str | None) -> str | None:
        if value is not None and any(
            unicodedata.category(character) in {"Cc", "Cf"} for character in value
        ):
            raise ValueError("flow edge label contains a control character")
        return value


class FlowViewportV2(ArtifactModel):
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    zoom: float = Field(ge=0.05, le=8.0, allow_inf_nan=False)


class FlowContentV2(ArtifactModel):
    schema_version: Literal[2] = 2
    kind: Literal["flow"] = "flow"
    nodes: list[FlowNodeV2] = Field(max_length=5_000)
    edges: list[FlowEdgeV2] = Field(max_length=10_000)
    viewport: FlowViewportV2

    @model_validator(mode="after")
    def validate_graph(self) -> FlowContentV2:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("flow contains duplicate node ids")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("flow contains duplicate edge ids")
        known = set(node_ids)
        adjacency = {node_id: [] for node_id in node_ids}
        incoming = {node_id: 0 for node_id in node_ids}
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"flow edge has unknown source: {edge.source}")
            if edge.target not in known:
                raise ValueError(f"flow edge has unknown target: {edge.target}")
            if edge.source == edge.target:
                raise ValueError("flow contains a self-loop")
            adjacency[edge.source].append(edge.target)
            incoming[edge.target] += 1
        pending = [node_id for node_id, count in incoming.items() if count == 0]
        visited = 0
        while pending:
            node_id = pending.pop()
            visited += 1
            for target in adjacency[node_id]:
                incoming[target] -= 1
                if incoming[target] == 0:
                    pending.append(target)
        if visited != len(node_ids):
            raise ValueError("flow must be acyclic")
        return self


class SpreadsheetCell(ArtifactModel):
    value: JsonValue
    style: dict[str, JsonValue] = Field(default_factory=dict)


class SpreadsheetSheet(ArtifactModel):
    id: BoundedId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    cells: dict[str, SpreadsheetCell] = Field(default_factory=dict)
    columns: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=16_384)

    @field_validator("cells")
    @classmethod
    def validate_cell_addresses(
        cls, value: dict[str, SpreadsheetCell]
    ) -> dict[str, SpreadsheetCell]:
        invalid = [key for key in value if re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", key) is None]
        if invalid:
            raise ValueError(f"invalid spreadsheet cell address: {invalid[0]}")
        return value


class SpreadsheetContentV1(ArtifactContentModel):
    kind: Literal["spreadsheet"] = "spreadsheet"
    calculation_mode: Literal["disabled"] = "disabled"
    sheets: list[SpreadsheetSheet] = Field(min_length=1, max_length=1_024)

    @model_validator(mode="after")
    def validate_workbook(self) -> SpreadsheetContentV1:
        sheet_ids = [sheet.id for sheet in self.sheets]
        if len(sheet_ids) != len(set(sheet_ids)):
            raise ValueError("spreadsheet contains duplicate sheet ids")
        non_empty_cells = sum(len(sheet.cells) for sheet in self.sheets)
        if non_empty_cells > 100_000:
            raise ValueError("spreadsheet exceeds 100000 non-empty cells")
        return self


def _valid_xlsx_address(address: str) -> bool:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", address)
    if match is None:
        return False
    column = 0
    for character in match.group(1):
        column = column * 26 + ord(character) - ord("A") + 1
    return column <= 16_384 and int(match.group(2)) <= 1_048_576


class SpreadsheetCellV2(ArtifactModel):
    value: str | int | float | bool | None

    @field_validator("value")
    @classmethod
    def validate_scalar(cls, value: str | int | float | bool | None):
        if isinstance(value, str) and len(value) > 32_767:
            raise ValueError("spreadsheet string cell exceeds 32767 characters")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not math.isfinite(value) or abs(value) > 1e15)
        ):
            raise ValueError("spreadsheet numeric cell is outside the deterministic range")
        return value


class SpreadsheetColumnV2(ArtifactModel):
    index: int = Field(ge=1, le=16_384)
    width: float = Field(default=120, ge=20, le=1_000, allow_inf_nan=False)
    hidden: bool = False


class SpreadsheetSheetV2(ArtifactModel):
    id: BoundedId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    cells: dict[str, SpreadsheetCellV2] = Field(default_factory=dict)
    columns: list[SpreadsheetColumnV2] = Field(default_factory=list, max_length=16_384)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
            raise ValueError("spreadsheet sheet name contains a control character")
        return value

    @field_validator("cells")
    @classmethod
    def validate_addresses(
        cls, value: dict[str, SpreadsheetCellV2]
    ) -> dict[str, SpreadsheetCellV2]:
        if any(not _valid_xlsx_address(address) for address in value):
            raise ValueError("spreadsheet cell address is outside XFD1048576")
        return value

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: list[SpreadsheetColumnV2]) -> list[SpreadsheetColumnV2]:
        indexes = [column.index for column in value]
        if len(indexes) != len(set(indexes)):
            raise ValueError("spreadsheet contains duplicate column indexes")
        return value


class SpreadsheetContentV2(ArtifactModel):
    kind: Literal["spreadsheet"] = "spreadsheet"
    schema_version: Literal[2] = 2
    calculation_mode: Literal["disabled"] = "disabled"
    sheets: list[SpreadsheetSheetV2] = Field(min_length=1, max_length=1_024)

    @model_validator(mode="after")
    def validate_workbook(self) -> SpreadsheetContentV2:
        sheet_ids = [sheet.id for sheet in self.sheets]
        if len(sheet_ids) != len(set(sheet_ids)):
            raise ValueError("spreadsheet contains duplicate sheet ids")
        if sum(len(sheet.cells) for sheet in self.sheets) > 100_000:
            raise ValueError("spreadsheet exceeds 100000 non-empty cells")
        return self


class CanvasContentV1(ArtifactContentModel):
    kind: Literal["canvas"] = "canvas"
    snapshot: dict[str, JsonValue]
    asset_ids: list[BoundedId] = Field(default_factory=list, max_length=10_000)
    embeds: Literal["deny"] = "deny"
    remote_assets: Literal["deny"] = "deny"

    @field_validator("snapshot")
    @classmethod
    def validate_snapshot(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if _contains_remote_url(value):
            raise ValueError("canvas snapshot contains a remote URL")
        return value


class CanvasObjectV2(ArtifactModel):
    id: BoundedId
    type: Literal["rectangle", "ellipse", "text", "line", "arrow", "note", "image"]
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)
    width: float = Field(gt=0, le=1_000_000)
    height: float = Field(gt=0, le=1_000_000)
    text: str | None = Field(default=None, max_length=10_000)
    asset_id: BoundedId | None = None

    @model_validator(mode="after")
    def validate_asset_usage(self) -> CanvasObjectV2:
        if self.type == "image" and self.asset_id is None:
            raise ValueError("canvas image requires an asset id")
        if self.type != "image" and self.asset_id is not None:
            raise ValueError("only canvas images may reference assets")
        return self


class CanvasSnapshotV2(ArtifactModel):
    objects: list[CanvasObjectV2] = Field(default_factory=list, max_length=10_000)

    @field_validator("objects")
    @classmethod
    def validate_unique_ids(cls, value: list[CanvasObjectV2]) -> list[CanvasObjectV2]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("canvas object ids must be unique")
        return value


class CanvasContentV2(ArtifactModel):
    kind: Literal["canvas"] = "canvas"
    schema_version: Literal[2] = 2
    snapshot: CanvasSnapshotV2
    asset_ids: list[BoundedId] = Field(default_factory=list, max_length=10_000)
    embeds: Literal["deny"] = "deny"
    remote_assets: Literal["deny"] = "deny"

    @model_validator(mode="after")
    def validate_assets(self) -> CanvasContentV2:
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("canvas asset ids must be unique")
        allowed = set(self.asset_ids)
        if any(item.asset_id not in allowed for item in self.snapshot.objects if item.asset_id):
            raise ValueError("canvas object references an unknown asset")
        return self


class SlidesContentV1(ArtifactContentModel):
    kind: Literal["slides"] = "slides"
    theme: dict[str, JsonValue] = Field(default_factory=dict)
    slides: list[dict[str, JsonValue]] = Field(max_length=200)
    allowed_element_types: ClassVar[set[str]] = {"text", "image", "shape", "line", "table", "chart"}

    @field_validator("slides")
    @classmethod
    def validate_slides(cls, value: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
        ids: set[str] = set()
        for slide in value:
            slide_id = slide.get("id")
            if not isinstance(slide_id, str) or not slide_id or slide_id in ids:
                raise ValueError("slides require unique string ids")
            ids.add(slide_id)
            elements = slide.get("elements", [])
            if not isinstance(elements, list):
                raise ValueError("slide elements must be an array")
            element_ids: set[str] = set()
            for element in elements:
                if not isinstance(element, dict):
                    raise ValueError("slide element must be an object")
                element_id = element.get("id")
                if not isinstance(element_id, str) or not element_id or element_id in element_ids:
                    raise ValueError("slide elements require unique string ids")
                element_ids.add(element_id)
                if element.get("type") not in cls.allowed_element_types:
                    raise ValueError(f"unsupported slide element type: {element.get('type')}")
                if _contains_remote_url(element):
                    raise ValueError("slide element contains a remote URL")
        return value


class SlideThemeV2(ArtifactModel):
    name: str = Field(min_length=1, max_length=100)
    background_color: str = Field(pattern=r"^[0-9A-F]{6}$")
    foreground_color: str = Field(pattern=r"^[0-9A-F]{6}$")
    accent_color: str = Field(pattern=r"^[0-9A-F]{6}$")


class SlideElementBaseV2(ArtifactModel):
    id: BoundedId
    x: float = Field(ge=0, le=13.333)
    y: float = Field(ge=0, le=7.5)
    width: float = Field(gt=0, le=13.333)
    height: float = Field(gt=0, le=7.5)

    @model_validator(mode="after")
    def validate_bounds(self) -> SlideElementBaseV2:
        if self.x + self.width > 13.333 or self.y + self.height > 7.5:
            raise ValueError("slide element exceeds the wide-layout bounds")
        return self


class SlideTextElementV2(SlideElementBaseV2):
    type: Literal["text"]
    text: str = Field(max_length=20_000)
    font_size: float = Field(default=18, ge=6, le=96)
    color: str | None = Field(default=None, pattern=r"^[0-9A-F]{6}$")
    bold: bool = False


class SlideImageElementV2(SlideElementBaseV2):
    type: Literal["image"]
    asset_id: BoundedId
    alt_text: str = Field(min_length=1, max_length=500)


class SlideShapeElementV2(SlideElementBaseV2):
    type: Literal["shape"]
    shape: Literal["rectangle", "ellipse"]
    fill_color: str = Field(default="FFFFFF", pattern=r"^[0-9A-F]{6}$")
    line_color: str = Field(default="172033", pattern=r"^[0-9A-F]{6}$")


class SlideLineElementV2(SlideElementBaseV2):
    type: Literal["line"]
    color: str = Field(default="172033", pattern=r"^[0-9A-F]{6}$")
    line_width: float = Field(default=1, gt=0, le=20)


class SlideTableElementV2(SlideElementBaseV2):
    type: Literal["table"]
    rows: list[list[str | float | bool | None]] = Field(min_length=1, max_length=100)

    @field_validator("rows")
    @classmethod
    def validate_rows(
        cls, value: list[list[str | float | bool | None]]
    ) -> list[list[str | float | bool | None]]:
        if any(not row or len(row) > 20 for row in value):
            raise ValueError("slide tables require 1 to 20 columns")
        width = len(value[0])
        if any(len(row) != width for row in value):
            raise ValueError("slide table rows must have equal widths")
        if any(isinstance(cell, str) and len(cell) > 5_000 for row in value for cell in row):
            raise ValueError("slide table cell text is too long")
        return value


class SlideChartSeriesV2(ArtifactModel):
    name: str = Field(min_length=1, max_length=100)
    values: list[float] = Field(min_length=1, max_length=100)

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: list[float]) -> list[float]:
        if any(not math.isfinite(item) or abs(item) > 1e15 for item in value):
            raise ValueError("slide chart values must be finite and bounded")
        return value


class SlideChartElementV2(SlideElementBaseV2):
    type: Literal["chart"]
    chart_type: Literal["bar", "line", "pie"]
    categories: list[str] = Field(min_length=1, max_length=100)
    series: list[SlideChartSeriesV2] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_series_lengths(self) -> SlideChartElementV2:
        if any(len(series.values) != len(self.categories) for series in self.series):
            raise ValueError("slide chart series must match category count")
        return self


SlideElementV2 = Annotated[
    SlideTextElementV2
    | SlideImageElementV2
    | SlideShapeElementV2
    | SlideLineElementV2
    | SlideTableElementV2
    | SlideChartElementV2,
    Field(discriminator="type"),
]


class SlideV2(ArtifactModel):
    id: BoundedId
    title: str | None = Field(default=None, max_length=200)
    elements: list[SlideElementV2] = Field(default_factory=list, max_length=500)

    @field_validator("elements")
    @classmethod
    def validate_unique_element_ids(cls, value: list[SlideElementV2]) -> list[SlideElementV2]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("slide element ids must be unique")
        return value


class SlidesContentV2(ArtifactModel):
    kind: Literal["slides"] = "slides"
    schema_version: Literal[2] = 2
    theme: SlideThemeV2
    slides: list[SlideV2] = Field(min_length=1, max_length=200)
    asset_ids: list[BoundedId] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def validate_deck(self) -> SlidesContentV2:
        slide_ids = [slide.id for slide in self.slides]
        if len(slide_ids) != len(set(slide_ids)):
            raise ValueError("slide ids must be unique")
        if len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("slide asset ids must be unique")
        allowed_assets = set(self.asset_ids)
        if any(
            element.asset_id not in allowed_assets
            for slide in self.slides
            for element in slide.elements
            if isinstance(element, SlideImageElementV2)
        ):
            raise ValueError("slide image references an unknown asset")
        return self


ArtifactContent = (
    DocumentContentV1
    | FormContentV1
    | CodeContentV1
    | CodeContentV2
    | FlowContentV1
    | FlowContentV2
    | SpreadsheetContentV1
    | SpreadsheetContentV2
    | CanvasContentV1
    | CanvasContentV2
    | SlidesContentV1
    | SlidesContentV2
)

ARTIFACT_CONTENT_MODEL_BY_KIND: dict[ArtifactKind, type[ArtifactContentModel]] = {
    ArtifactKind.DOCUMENT: DocumentContentV1,
    ArtifactKind.FORM: FormContentV1,
    ArtifactKind.CODE: CodeContentV1,
    ArtifactKind.FLOW: FlowContentV1,
    ArtifactKind.SPREADSHEET: SpreadsheetContentV1,
    ArtifactKind.CANVAS: CanvasContentV1,
    ArtifactKind.SLIDES: SlidesContentV1,
}

ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION: dict[
    tuple[ArtifactKind, int], type[ArtifactModel]
] = {
    **{(kind, 1): model for kind, model in ARTIFACT_CONTENT_MODEL_BY_KIND.items()},
    (ArtifactKind.CODE, 2): CodeContentV2,
    (ArtifactKind.FLOW, 2): FlowContentV2,
    (ArtifactKind.SPREADSHEET, 2): SpreadsheetContentV2,
    (ArtifactKind.CANVAS, 2): CanvasContentV2,
    (ArtifactKind.SLIDES, 2): SlidesContentV2,
}


class SafeJsonPatchOperation(ArtifactModel):
    op: Literal["add", "remove", "replace", "test"]
    path: Annotated[
        str, StringConstraints(min_length=1, max_length=512, pattern=r"^/", strict=True)
    ]
    value: JsonValue | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        segments = value[1:].split("/")
        decoded = [segment.replace("~1", "/").replace("~0", "~") for segment in segments]
        if any(segment in {"__proto__", "prototype", "constructor"} for segment in decoded):
            raise ValueError("unsafe JSON Pointer segment")
        if any("~" in segment.replace("~0", "").replace("~1", "") for segment in segments):
            raise ValueError("invalid JSON Pointer escape")
        return value

    @model_validator(mode="after")
    def validate_value_presence(self) -> SafeJsonPatchOperation:
        if self.op in {"add", "replace", "test"} and "value" not in self.model_fields_set:
            raise ValueError(f"{self.op} operation requires value")
        if self.op == "remove" and "value" in self.model_fields_set:
            raise ValueError("remove operation cannot include value")
        return self


class SafeJsonPatch(ArtifactModel):
    operations: list[SafeJsonPatchOperation] = Field(min_length=1, max_length=100)


def validate_artifact_content(
    kind: ArtifactKind,
    payload: object,
    *,
    schema_version: int | None = None,
) -> ArtifactModel:
    observed_version = schema_version
    if observed_version is None and isinstance(payload, dict):
        value = payload.get("schemaVersion")
        if isinstance(value, int) and not isinstance(value, bool):
            observed_version = value
    if observed_version is None:
        observed_version = 1
    model = ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION.get((kind, observed_version))
    if model is None:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_SCHEMA_VERSION_UNSUPPORTED,
            "artifact content schema version is unsupported",
            details={"kind": kind.value, "schemaVersion": observed_version},
        )
    content = model.model_validate(payload)
    serialized = json.dumps(
        content.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    limit = ARTIFACT_CONTENT_LIMITS_BYTES[kind]
    if len(serialized) > limit:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_CONTENT_TOO_LARGE,
            f"{kind.value} content exceeds {limit} bytes",
            details={"kind": kind.value, "limitBytes": limit, "observedBytes": len(serialized)},
        )
    return content
