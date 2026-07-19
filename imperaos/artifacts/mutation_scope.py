from __future__ import annotations

from copy import deepcopy
from typing import Any

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import ArtifactKind


def require_scoped_replacement(
    kind: ArtifactKind,
    base: dict[str, Any],
    proposed: dict[str, Any],
    selection: dict[str, Any],
) -> None:
    if selection.get("kind") != kind.value:
        _deny()
    validators = {
        ArtifactKind.DOCUMENT: _document,
        ArtifactKind.FORM: _form,
        ArtifactKind.CODE: _code,
        ArtifactKind.FLOW: _flow,
        ArtifactKind.SPREADSHEET: _spreadsheet,
        ArtifactKind.CANVAS: _canvas,
        ArtifactKind.SLIDES: _slides,
    }
    try:
        valid = validators[kind](base, proposed, selection)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        _deny()


def _same_except(base: dict[str, Any], proposed: dict[str, Any], key: str) -> bool:
    left, right = deepcopy(base), deepcopy(proposed)
    left.pop(key, None)
    right.pop(key, None)
    return left == right


def _document(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    ids = set(selection["blockIds"])
    left, right = base["blocks"], proposed["blocks"]
    return (
        bool(ids)
        and _same_except(base, proposed, "blocks")
        and ids.issubset({item.get("id") for item in left})
        and ids.issubset({item.get("id") for item in right})
        and [item for item in left if item.get("id") not in ids]
        == [item for item in right if item.get("id") not in ids]
    )


def _form(
    base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]
) -> bool:
    paths = selection["fieldPaths"]
    if not paths or not _same_except(base, proposed, "schema"):
        return False
    left_schema, right_schema = deepcopy(base["schema"]), deepcopy(proposed["schema"])
    if not _same_except(left_schema, right_schema, "properties"):
        return False
    left, right = left_schema["properties"], right_schema["properties"]
    for pointer in paths:
        parts = _pointer_parts(pointer)
        if not parts or parts[0] not in left or parts[0] not in right:
            return False
        _mask_form_field(left, parts)
        _mask_form_field(right, parts)
    return left == right


def _code(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    if not _same_except(base, proposed, "text"):
        return False
    text = base["text"]
    start = _line_offset(text, selection["startLineNumber"], selection["startColumn"])
    end = _line_offset(text, selection["endLineNumber"], selection["endColumn"])
    return proposed["text"].startswith(text[:start]) and proposed["text"].endswith(text[end:])


def _line_offset(text: str, line: int, column: int) -> int:
    lines = text.splitlines(keepends=True)
    if line > len(lines):
        raise ValueError
    return sum(len(value) for value in lines[: line - 1]) + column - 1


def _flow(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    if not _same_except(_without(base, "nodes"), _without(proposed, "nodes"), "edges"):
        return False
    node_ids, edge_ids = set(selection.get("nodeIds", [])), set(selection.get("edgeIds", []))
    return (
        [item for item in base["nodes"] if item.get("id") not in node_ids]
        == [item for item in proposed["nodes"] if item.get("id") not in node_ids]
        and [item for item in base["edges"] if item.get("id") not in edge_ids]
        == [item for item in proposed["edges"] if item.get("id") not in edge_ids]
    )


def _spreadsheet(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    if not _same_except(base, proposed, "sheets"):
        return False
    sheet_id = selection["sheetId"]
    allowed = _expanded_ranges(selection["ranges"])
    return _strip_cells(base["sheets"], sheet_id, allowed) == _strip_cells(
        proposed["sheets"], sheet_id, allowed
    )


def _canvas(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    ids = set(selection["objectIds"])
    if (
        not ids
        or base.get("schemaVersion") != 2
        or proposed.get("schemaVersion") != 2
        or not _same_except(base, proposed, "snapshot")
    ):
        return False
    left_snapshot, right_snapshot = base["snapshot"], proposed["snapshot"]
    if not _same_except(left_snapshot, right_snapshot, "objects"):
        return False
    left, right = left_snapshot["objects"], right_snapshot["objects"]
    if not ids.issubset({item.get("id") for item in left}) or not ids.issubset(
        {item.get("id") for item in right}
    ):
        return False
    return [item for item in left if item.get("id") not in ids] == [
        item for item in right if item.get("id") not in ids
    ]


def _pointer_parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError
    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in pointer[1:].split("/")
    ]


def _mask_pointer(root: dict[str, Any], parts: list[str]) -> None:
    parent: Any = root
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    if isinstance(parent, list):
        parent[int(parts[-1])] = "__ARTIFACT_SELECTED__"
    else:
        parent[parts[-1]] = "__ARTIFACT_SELECTED__"


def _mask_form_field(properties: dict[str, Any], parts: list[str]) -> None:
    current = properties
    for index, part in enumerate(parts):
        if part not in current:
            raise ValueError
        if index == len(parts) - 1:
            current[part] = "__ARTIFACT_SELECTED__"
            return
        field = current[part]
        if not isinstance(field, dict) or not isinstance(field.get("properties"), dict):
            raise ValueError
        current = field["properties"]


def _slides(base: dict[str, Any], proposed: dict[str, Any], selection: dict[str, Any]) -> bool:
    if not _same_except(base, proposed, "slides"):
        return False
    slide_id, element_id = selection["slideId"], selection.get("elementId")
    if element_id is None:
        return [item for item in base["slides"] if item.get("id") != slide_id] == [
            item for item in proposed["slides"] if item.get("id") != slide_id
        ]
    left, right = deepcopy(base["slides"]), deepcopy(proposed["slides"])
    for slides in (left, right):
        slide = next(item for item in slides if item.get("id") == slide_id)
        slide["elements"] = [item for item in slide["elements"] if item.get("id") != element_id]
    return left == right


def _without(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop(key, None)
    return result


def _strip_cells(
    sheets: list[dict[str, Any]], sheet_id: str, allowed: set[str]
) -> list[dict[str, Any]]:
    result = deepcopy(sheets)
    sheet = next(item for item in result if item.get("id") == sheet_id)
    sheet["cells"] = {
        address: value
        for address, value in sheet.get("cells", {}).items()
        if address not in allowed
    }
    return result


def _expanded_ranges(ranges: list[str]) -> set[str]:
    result: set[str] = set()
    for value in ranges:
        start, _, end = value.partition(":")
        end = end or start
        start_col, start_row = _cell(start)
        end_col, end_row = _cell(end)
        if (end_row - start_row + 1) * (end_col - start_col + 1) > 10_000:
            raise ValueError
        for row in range(start_row, end_row + 1):
            for col in range(start_col, end_col + 1):
                result.add(f"{_column(col)}{row}")
    return result


def _cell(value: str) -> tuple[int, int]:
    letters = "".join(char for char in value if char.isalpha())
    row = int(value[len(letters) :])
    col = 0
    for char in letters:
        col = col * 26 + ord(char) - 64
    return col, row


def _column(value: int) -> str:
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _deny() -> None:
    raise ArtifactDomainError(
        ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
        "artifact proposal changes content outside the trusted selection",
        details={"reasonCode": "ARTIFACT_PROPOSAL_SCOPE_EXCEEDED"},
    )
