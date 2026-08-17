from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from imperaos.product_identity import PRODUCT_IDENTITY, load_product_identity

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PATH = REPO_ROOT / "branding" / "identity.json"
SCHEMA_PATH = REPO_ROOT / "contracts" / "rebrand" / "brand_identity.schema.json"
TYPESCRIPT_PATH = REPO_ROOT / "apps" / "operator-panel" / "src" / "productIdentity.ts"
NAMING_STANDARD_PATH = REPO_ROOT / "docs" / "IMPERAOS_NAMING_STANDARD.md"

EXPECTED_IDENTITY = {
    "displayName": "ImperaOS",
    "slug": "imperaos",
    "pythonDistribution": "imperaos",
    "pythonPackage": "imperaos",
    "cliName": "imperaos",
    "envPrefix": "IMPERAOS",
    "stateRoot": ".imperaos",
    "operatorProductName": "ImperaOS Operator Panel",
    "operatorBundleId": "com.imperaos.operatorpanel",
    "runtimeResourceDir": "imperaos-runtime",
    "domain": "imperaos.com",
    "repository": "bakiacikgoz/ImperaOS",
    "metricPrefix": "imperaos_",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_identity_has_exact_values_and_validates_against_schema() -> None:
    identity = _load_json(IDENTITY_PATH)
    schema = _load_json(SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(identity)

    assert identity == EXPECTED_IDENTITY
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(EXPECTED_IDENTITY)
    assert set(schema["properties"]) == set(EXPECTED_IDENTITY)
    assert {
        field: definition["const"]
        for field, definition in schema["properties"].items()
    } == EXPECTED_IDENTITY


def test_schema_rejects_incorrect_display_name_casing() -> None:
    invalid_display_name = "".join(("Impera", "O", "s"))
    invalid_identity = EXPECTED_IDENTITY | {"displayName": invalid_display_name}

    with pytest.raises(ValidationError):
        Draft202012Validator(_load_json(SCHEMA_PATH)).validate(invalid_identity)


def test_naming_standard_distinguishes_stored_stems_from_rendered_forms() -> None:
    naming_standard = NAMING_STANDARD_PATH.read_text(encoding="utf-8")

    assert (
        "The canonical `envPrefix` value stores the stem `IMPERAOS` without a trailing underscore."
        in naming_standard
    )
    assert "Rendered environment keys use `IMPERAOS_<SUFFIX>`." in naming_standard
    assert (
        "The canonical `stateRoot` value stores the root `.imperaos` without a trailing slash."
        in naming_standard
    )
    assert "Child paths render beneath it as `.imperaos/...`." in naming_standard


def test_typescript_identity_is_a_typed_frozen_view_of_canonical_json() -> None:
    identity = _load_json(IDENTITY_PATH)
    source = TYPESCRIPT_PATH.read_text(encoding="utf-8")

    import_match = re.fullmatch(
        r'import canonicalProductIdentity from "(?P<path>[^"\r\n]+)" '
        r'with \{ type: "json" \};\n\n'
        r"export type ProductIdentity = Readonly<\{\n"
        r"(?P<fields>(?:  [A-Za-z][A-Za-z0-9]*: string;\n)+)"
        r"\}>;\n\n"
        r"export const PRODUCT_IDENTITY: ProductIdentity = "
        r"Object\.freeze\(canonicalProductIdentity\);\n",
        source,
    )
    assert import_match is not None, (
        "TypeScript identity module must keep the typed direct-import form"
    )

    imported_path = (TYPESCRIPT_PATH.parent / import_match.group("path")).resolve()
    assert imported_path == IDENTITY_PATH.resolve()
    assert _load_json(imported_path) == identity

    field_names = [
        line.removeprefix("  ").removesuffix(": string;")
        for line in import_match.group("fields").splitlines()
    ]
    assert field_names == list(identity)


def test_python_identity_is_a_typed_frozen_view_of_canonical_json() -> None:
    assert load_product_identity() == PRODUCT_IDENTITY
    assert PRODUCT_IDENTITY.to_canonical_dict() == _load_json(IDENTITY_PATH)


def test_python_identity_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        PRODUCT_IDENTITY.slug = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda identity: identity.pop("slug"), "missing fields"),
        (lambda identity: identity.update({"extra": "value"}), "unexpected fields"),
        (lambda identity: identity.update({"slug": 1}), "must be strings"),
        (
            lambda identity: identity.update(
                {"pythonPackage": "".join(("bin", "liquid"))}
            ),
            "canonical values",
        ),
    ],
)
def test_python_identity_rejects_invalid_projections(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    invalid_identity = EXPECTED_IDENTITY.copy()
    mutation(invalid_identity)
    invalid_path = tmp_path / "identity.json"
    invalid_path.write_text(json.dumps(invalid_identity), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_product_identity(invalid_path)
