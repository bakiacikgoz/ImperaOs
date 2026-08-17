from __future__ import annotations

from copy import deepcopy

import pytest

from imperaos.artifacts.errors import ArtifactDomainError
from imperaos.artifacts.models import ArtifactKind
from imperaos.artifacts.mutation_scope import require_scoped_replacement


def test_form_scope_allows_only_selected_schema_property() -> None:
    base = {
        "kind": "form",
        "schemaVersion": 1,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name"},
                "fixed": {"type": "string", "title": "Fixed"},
            },
            "additionalProperties": False,
        },
        "behavior": {"submitMode": "explicit", "externalContinuation": "deny"},
    }
    selected = deepcopy(base)
    selected["schema"]["properties"]["name"]["title"] = "Full name"
    require_scoped_replacement(
        ArtifactKind.FORM,
        base,
        selected,
        {"kind": "form", "fieldPaths": ["/name"]},
    )

    escaped = deepcopy(selected)
    escaped["schema"]["properties"]["fixed"]["title"] = "Changed"
    with pytest.raises(ArtifactDomainError):
        require_scoped_replacement(
            ArtifactKind.FORM,
            base,
            escaped,
            {"kind": "form", "fieldPaths": ["/name"]},
        )


def test_form_scope_maps_nested_field_paths_through_schema_properties() -> None:
    base = {
        "kind": "form",
        "schemaVersion": 1,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "title": "Name"},
                        "fixed": {"type": "string", "title": "Fixed"},
                    },
                }
            },
        },
        "behavior": {"submitMode": "explicit", "externalContinuation": "deny"},
    }
    selected = deepcopy(base)
    selected["schema"]["properties"]["profile"]["properties"]["name"]["title"] = "Full name"
    require_scoped_replacement(
        ArtifactKind.FORM,
        base,
        selected,
        {"kind": "form", "fieldPaths": ["/profile/name"]},
    )

    escaped = deepcopy(selected)
    escaped["schema"]["properties"]["profile"]["properties"]["fixed"]["title"] = "Changed"
    with pytest.raises(ArtifactDomainError):
        require_scoped_replacement(
            ArtifactKind.FORM,
            base,
            escaped,
            {"kind": "form", "fieldPaths": ["/profile/name"]},
        )


def test_canvas_v2_scope_allows_only_selected_snapshot_objects() -> None:
    base = {
        "kind": "canvas",
        "schemaVersion": 2,
        "snapshot": {
            "objects": [
                {"id": "shape-1", "type": "rectangle", "x": 0, "y": 0},
                {"id": "shape-2", "type": "rectangle", "x": 10, "y": 10},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "assetIds": [],
        "embeds": "deny",
        "remoteAssets": "deny",
    }
    selected = deepcopy(base)
    selected["snapshot"]["objects"][0]["x"] = 25
    require_scoped_replacement(
        ArtifactKind.CANVAS,
        base,
        selected,
        {"kind": "canvas", "objectIds": ["shape-1"]},
    )

    escaped = deepcopy(selected)
    escaped["snapshot"]["objects"][1]["x"] = 30
    with pytest.raises(ArtifactDomainError):
        require_scoped_replacement(
            ArtifactKind.CANVAS,
            base,
            escaped,
            {"kind": "canvas", "objectIds": ["shape-1"]},
        )

    metadata_escape = deepcopy(selected)
    metadata_escape["snapshot"]["viewport"]["zoom"] = 2
    with pytest.raises(ArtifactDomainError):
        require_scoped_replacement(
            ArtifactKind.CANVAS,
            base,
            metadata_escape,
            {"kind": "canvas", "objectIds": ["shape-1"]},
        )

    missing = deepcopy(base)
    missing["snapshot"]["objects"] = [missing["snapshot"]["objects"][1]]
    with pytest.raises(ArtifactDomainError):
        require_scoped_replacement(
            ArtifactKind.CANVAS,
            base,
            missing,
            {"kind": "canvas", "objectIds": ["shape-1"]},
        )
