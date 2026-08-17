from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from imperaos.artifacts.content import (
    ARTIFACT_CONTENT_MODEL_BY_KIND,
    ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION,
    SafeJsonPatch,
    validate_artifact_content,
)
from imperaos.artifacts.models import ArtifactKind

VALID_CONTENT: dict[ArtifactKind, dict[str, object]] = {
    ArtifactKind.DOCUMENT: {
        "kind": "document",
        "schemaVersion": 1,
        "language": "tr",
        "pageMode": "document",
        "blocks": [
            {"id": "block-1", "type": "paragraph", "content": [{"type": "text", "text": "Merhaba"}]}
        ],
    },
    ArtifactKind.FORM: {
        "kind": "form",
        "schemaVersion": 1,
        "schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "maxLength": 100}},
            "required": ["name"],
            "additionalProperties": False,
        },
        "uiSchema": {"name": {"ui:widget": "text"}},
        "behavior": {"submitMode": "explicit", "externalContinuation": "approval_required"},
        "sensitivePaths": ["/name"],
    },
    ArtifactKind.CODE: {
        "kind": "code",
        "schemaVersion": 1,
        "filename": "main.py",
        "language": "python",
        "text": "print('display only')\n",
        "lineEnding": "lf",
        "executionPolicy": "deny",
    },
    ArtifactKind.FLOW: {
        "kind": "flow",
        "schemaVersion": 1,
        "nodes": [
            {
                "id": "node-1",
                "type": "input",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start"},
            },
            {
                "id": "node-2",
                "type": "output",
                "position": {"x": 100, "y": 0},
                "data": {"label": "End"},
            },
        ],
        "edges": [{"id": "edge-1", "source": "node-1", "target": "node-2"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
    ArtifactKind.SPREADSHEET: {
        "kind": "spreadsheet",
        "schemaVersion": 1,
        "calculationMode": "disabled",
        "sheets": [
            {"id": "sheet-1", "name": "Sheet 1", "cells": {"A1": {"value": "Safe"}}, "columns": []}
        ],
    },
    ArtifactKind.CANVAS: {
        "kind": "canvas",
        "schemaVersion": 1,
        "snapshot": {"store": {"shape:1": {"typeName": "shape", "assetId": "asset-1"}}},
        "assetIds": ["asset-1"],
        "embeds": "deny",
        "remoteAssets": "deny",
    },
    ArtifactKind.SLIDES: {
        "kind": "slides",
        "schemaVersion": 1,
        "theme": {"name": "ImperaOS"},
        "slides": [
            {"id": "slide-1", "elements": [{"id": "element-1", "type": "text", "text": "Title"}]}
        ],
    },
}


@pytest.mark.parametrize("kind", list(ArtifactKind))
def test_each_v1_artifact_content_schema_accepts_its_minimal_contract(kind: ArtifactKind) -> None:
    content = validate_artifact_content(kind, VALID_CONTENT[kind])

    assert content.kind == kind.value
    assert content.schema_version == 1


def test_artifact_content_registry_is_complete_and_kind_discriminated() -> None:
    assert set(ARTIFACT_CONTENT_MODEL_BY_KIND) == set(ArtifactKind)

    mismatched = dict(VALID_CONTENT[ArtifactKind.CODE])
    mismatched["kind"] = "document"
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.CODE, mismatched)


def test_code_content_registry_dispatches_by_schema_version() -> None:
    legacy = dict(VALID_CONTENT[ArtifactKind.CODE])
    legacy["language"] = "tsx"
    assert validate_artifact_content(ArtifactKind.CODE, legacy).schema_version == 1

    strict = {**legacy, "schemaVersion": 2}
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.CODE, strict)

    assert (ArtifactKind.CODE, 1) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION
    assert (ArtifactKind.CODE, 2) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION


def test_safe_json_patch_rejects_prototype_pollution_and_unsafe_operations() -> None:
    patch = SafeJsonPatch.model_validate(
        {"operations": [{"op": "replace", "path": "/blocks/0/content/0/text", "value": "Updated"}]}
    )
    assert patch.operations[0].op == "replace"

    with pytest.raises(ValidationError, match="unsafe JSON Pointer"):
        SafeJsonPatch.model_validate(
            {"operations": [{"op": "add", "path": "/metadata/__proto__/polluted", "value": True}]}
        )
    with pytest.raises(ValidationError):
        SafeJsonPatch.model_validate(
            {"operations": [{"op": "move", "path": "/safe", "from": "/other"}]}
        )


def test_form_schema_rejects_remote_refs_eval_pressure_and_network_widgets() -> None:
    remote_ref = dict(VALID_CONTENT[ArtifactKind.FORM])
    remote_ref["schema"] = {
        "type": "object",
        "properties": {"name": {"$ref": "https://example.com/schema.json"}},
    }
    with pytest.raises(ValidationError, match="remote refs"):
        validate_artifact_content(ArtifactKind.FORM, remote_ref)

    unsafe_pattern = dict(VALID_CONTENT[ArtifactKind.FORM])
    unsafe_pattern["schema"] = {
        "type": "object",
        "properties": {"value": {"type": "string", "pattern": "(a+)+$"}},
    }
    with pytest.raises(ValidationError, match="unsafe pattern"):
        validate_artifact_content(ArtifactKind.FORM, unsafe_pattern)

    network_widget = dict(VALID_CONTENT[ArtifactKind.FORM])
    network_widget["uiSchema"] = {"name": {"ui:widget": "html", "src": "https://example.com"}}
    with pytest.raises(ValidationError, match="uiSchema"):
        validate_artifact_content(ArtifactKind.FORM, network_widget)


def test_editor_schemas_keep_execution_calculation_and_remote_assets_disabled() -> None:
    executable = dict(VALID_CONTENT[ArtifactKind.CODE])
    executable["executionPolicy"] = "allow"
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.CODE, executable)

    calculated = dict(VALID_CONTENT[ArtifactKind.SPREADSHEET])
    calculated["calculationMode"] = "automatic"
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.SPREADSHEET, calculated)

    remote_canvas = dict(VALID_CONTENT[ArtifactKind.CANVAS])
    remote_canvas["snapshot"] = {"asset": {"src": "https://example.com/image.png"}}
    with pytest.raises(ValidationError, match="remote URL"):
        validate_artifact_content(ArtifactKind.CANVAS, remote_canvas)


def test_code_content_matches_shared_parity_fixture() -> None:
    fixture = json.loads(
        Path("contracts/artifacts/fixtures/code-content-parity.v1.json").read_text(encoding="utf-8")
    )

    for case in fixture["cases"]:
        try:
            validate_artifact_content(ArtifactKind.CODE, case["content"])
            accepted = True
        except ValidationError:
            accepted = False
        assert accepted is case["expectedValid"], case["id"]


def test_flow_edges_and_slide_count_are_bounded() -> None:
    invalid_flow = dict(VALID_CONTENT[ArtifactKind.FLOW])
    invalid_flow["edges"] = [{"id": "edge-bad", "source": "node-1", "target": "missing"}]
    with pytest.raises(ValidationError, match="unknown target"):
        validate_artifact_content(ArtifactKind.FLOW, invalid_flow)

    too_many_slides = dict(VALID_CONTENT[ArtifactKind.SLIDES])
    too_many_slides["slides"] = [{"id": f"slide-{index}", "elements": []} for index in range(201)]
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.SLIDES, too_many_slides)


def test_flow_v2_is_strict_bounded_and_acyclic() -> None:
    strict = {**VALID_CONTENT[ArtifactKind.FLOW], "schemaVersion": 2}
    assert validate_artifact_content(ArtifactKind.FLOW, strict).schema_version == 2

    cyclic = {
        **strict,
        "edges": [
            {"id": "edge-1", "source": "node-1", "target": "node-2"},
            {"id": "edge-2", "source": "node-2", "target": "node-1"},
        ],
    }
    with pytest.raises(ValidationError, match="acyclic"):
        validate_artifact_content(ArtifactKind.FLOW, cyclic)

    self_loop = {**strict, "edges": [{"id": "edge-1", "source": "node-1", "target": "node-1"}]}
    with pytest.raises(ValidationError, match="self-loop"):
        validate_artifact_content(ArtifactKind.FLOW, self_loop)

    unknown_data = {
        **strict,
        "nodes": [
            {
                "id": "node-1",
                "type": "input",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start", "url": "https://example.com"},
            }
        ],
        "edges": [],
    }
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.FLOW, unknown_data)

    missing_artifact_binding = {
        **strict,
        "nodes": [
            {
                "id": "node-1",
                "type": "artifact",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Linked artifact"},
            }
        ],
        "edges": [],
    }
    with pytest.raises(ValidationError, match="artifactId"):
        validate_artifact_content(ArtifactKind.FLOW, missing_artifact_binding)

    assert (ArtifactKind.FLOW, 1) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION
    assert (ArtifactKind.FLOW, 2) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION


def test_canvas_v2_is_strict_bounded_and_asset_referential() -> None:
    content = {
        "kind": "canvas",
        "schemaVersion": 2,
        "snapshot": {
            "objects": [
                {
                    "id": "shape-1", "type": "rectangle", "x": 10, "y": 20,
                    "width": 200, "height": 100, "text": "Local note",
                },
                {
                    "id": "image-1", "type": "image", "x": 0, "y": 0,
                    "width": 80, "height": 80, "assetId": "asset-1",
                },
            ]
        },
        "assetIds": ["asset-1"],
        "embeds": "deny",
        "remoteAssets": "deny",
    }
    assert validate_artifact_content(ArtifactKind.CANVAS, content).schema_version == 2
    assert (ArtifactKind.CANVAS, 2) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION

    shape = content["snapshot"]["objects"][0]
    image = content["snapshot"]["objects"][1]
    cases = [
        {**content, "snapshot": {"objects": [shape, shape]}},
        {**content, "snapshot": {"objects": [{**image, "assetId": "missing"}]}},
        {**content, "snapshot": {"objects": [{**shape, "src": "https://example.com/x"}]}},
        {**content, "snapshot": {"objects": [{**shape, "x": float("nan")}]}},
        {**content, "snapshot": {"objects": [{**shape, "type": "embed"}]}},
    ]
    for invalid in cases:
        with pytest.raises(ValidationError):
            validate_artifact_content(ArtifactKind.CANVAS, invalid)


def test_slides_v2_is_structured_strict_and_asset_referential() -> None:
    deck = {
        "kind": "slides", "schemaVersion": 2,
        "theme": {
            "name": "ImperaOS", "backgroundColor": "FFFFFF",
            "foregroundColor": "172033", "accentColor": "6E57FF",
        },
        "slides": [{
            "id": "slide-1", "title": "Overview",
            "elements": [
                {
                    "id": "title-1", "type": "text", "x": 0.5, "y": 0.5,
                    "width": 8, "height": 1, "text": "Governed deck", "fontSize": 30,
                },
                {
                    "id": "image-1", "type": "image", "x": 8.8, "y": 0.5,
                    "width": 3.5, "height": 2.5, "assetId": "asset-1",
                    "altText": "Local evidence image",
                },
            ],
        }],
        "assetIds": ["asset-1"],
    }
    assert validate_artifact_content(ArtifactKind.SLIDES, deck).schema_version == 2
    assert (ArtifactKind.SLIDES, 2) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION

    invalid_cases = [
        {**deck, "slides": [deck["slides"][0], deck["slides"][0]]},
        {**deck, "slides": [{**deck["slides"][0], "elements": [
            deck["slides"][0]["elements"][0], deck["slides"][0]["elements"][0],
        ]}]},
        {**deck, "slides": [{**deck["slides"][0], "elements": [{
            **deck["slides"][0]["elements"][1], "assetId": "missing",
        }]}]},
        {**deck, "slides": [{**deck["slides"][0], "elements": [{
            **deck["slides"][0]["elements"][0], "type": "video",
        }]}]},
        {**deck, "slides": [{**deck["slides"][0], "externalUrl": "https://example.com"}]},
    ]
    for invalid in invalid_cases:
        with pytest.raises(ValidationError):
            validate_artifact_content(ArtifactKind.SLIDES, invalid)

def test_spreadsheet_v2_is_strict_scalar_and_xlsx_bounded() -> None:
    strict = {
        "kind": "spreadsheet", "schemaVersion": 2, "calculationMode": "disabled",
        "sheets": [{
            "id": "sheet-1", "name": "Sheet 1",
            "cells": {"XFD1048576": {"value": "last"}, "A1": {"value": 1.5}},
            "columns": [{"index": 1, "width": 120, "hidden": False}],
        }],
    }
    assert validate_artifact_content(ArtifactKind.SPREADSHEET, strict).schema_version == 2

    for address in ("XFE1", "A1048577", "A0"):
        invalid = {**strict, "sheets": [{**strict["sheets"][0], "cells": {address: {"value": 1}}}]}
        with pytest.raises(ValidationError, match="XFD1048576"):
            validate_artifact_content(ArtifactKind.SPREADSHEET, invalid)

    invalid_value = {
        **strict,
        "sheets": [{**strict["sheets"][0], "cells": {"A1": {"value": {"formula": "=1+1"}}}}],
    }
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.SPREADSHEET, invalid_value)

    unknown_cell_field = {
        **strict,
        "sheets": [{**strict["sheets"][0], "cells": {"A1": {"value": 1, "formula": "=1+1"}}}],
    }
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.SPREADSHEET, unknown_cell_field)

    assert (ArtifactKind.SPREADSHEET, 1) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION
    assert (ArtifactKind.SPREADSHEET, 2) in ARTIFACT_CONTENT_MODEL_BY_KIND_VERSION
