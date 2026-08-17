from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from imperaos.artifacts.content import validate_artifact_content
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.forms import validate_form_response
from imperaos.artifacts.models import ArtifactKind
from imperaos.artifacts.service import ArtifactService

FIXTURE = (
    Path(__file__).parents[1]
    / "contracts"
    / "artifacts"
    / "fixtures"
    / "form-schema-parity.v1.json"
)
RESPONSE_FIXTURE = FIXTURE.with_name("form-response-parity.v1.json")


def _form(schema: dict[str, object], **extra: object) -> dict[str, object]:
    return {"kind": "form", "schemaVersion": 1, "schema": schema, **extra}


def _nested_schema(levels: int) -> dict[str, object]:
    node: dict[str, object] = {"type": "string"}
    for index in reversed(range(levels)):
        node = {"type": "object", "properties": {f"level_{index}": node}}
    return node


def test_form_schema_parity_fixture_matches_authoritative_backend() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["version"] == 1
    for case in fixture["cases"]:
        if case["allowed"]:
            validate_artifact_content(ArtifactKind.FORM, case["content"])
        else:
            with pytest.raises(ValidationError):
                validate_artifact_content(ArtifactKind.FORM, case["content"])


def test_form_response_parity_fixture_matches_authoritative_backend() -> None:
    fixture = json.loads(RESPONSE_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["version"] == 1
    for case in fixture["cases"]:
        if case["allowed"]:
            validate_form_response(case["schema"], case["response"])
        else:
            with pytest.raises(ArtifactDomainError) as caught:
                validate_form_response(case["schema"], case["response"])
            assert caught.value.code is ArtifactErrorCode.FORM_VALIDATION_FAILED


def test_form_schema_boundaries_accept_100_fields_and_depth_6() -> None:
    fields = {f"field_{index}": {"type": "string"} for index in range(100)}
    validate_artifact_content(
        ArtifactKind.FORM,
        _form({"type": "object", "properties": fields}),
    )
    validate_artifact_content(ArtifactKind.FORM, _form(_nested_schema(5)))


def test_form_schema_boundaries_reject_101_fields_and_depth_7() -> None:
    fields = {f"field_{index}": {"type": "string"} for index in range(101)}
    with pytest.raises(ValidationError, match="100 fields"):
        validate_artifact_content(
            ArtifactKind.FORM,
            _form({"type": "object", "properties": fields}),
        )
    with pytest.raises(ValidationError, match="depth exceeds 6"):
        validate_artifact_content(ArtifactKind.FORM, _form(_nested_schema(6)))


def test_form_schema_failure_uses_bounded_code_without_echoing_values(tmp_path: Path) -> None:
    private_marker = "private-form-value-canary"
    unsafe = _form({"$ref": f"https://invalid.example/{private_marker}"})
    with pytest.raises(ArtifactDomainError) as caught:
        ArtifactService(tmp_path / "artifacts")._validate_content(ArtifactKind.FORM, unsafe)

    assert caught.value.code is ArtifactErrorCode.FORM_SCHEMA_UNSAFE
    assert private_marker not in caught.value.message
    assert private_marker not in json.dumps(caught.value.details)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": 7},
        {"$schema": "https://json-schema.org/draft/2020-12/schema"},
        {"type": "string", "pattern": "(a|aa)+$"},
        {
            "$ref": "#/definitions/a",
            "definitions": {
                "a": {"$ref": "#/definitions/b"},
                "b": {"$ref": "#/definitions/a"},
            },
        },
    ],
)
def test_form_schema_rejects_invalid_draft7_and_unsafe_cycles(schema: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_artifact_content(ArtifactKind.FORM, _form(schema))
