"""Typed Python projection of the canonical ImperaOS product identity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final

_CANONICAL_IDENTITY_PATH: Final = (
    Path(__file__).resolve().parents[1] / "branding" / "identity.json"
)
_FIELD_SPECS: Final = (
    ("displayName", "display_name", "ImperaOS"),
    ("slug", "slug", "imperaos"),
    ("pythonDistribution", "python_distribution", "imperaos"),
    ("pythonPackage", "python_package", "imperaos"),
    ("cliName", "cli_name", "imperaos"),
    ("envPrefix", "env_prefix", "IMPERAOS"),
    ("stateRoot", "state_root", ".imperaos"),
    ("operatorProductName", "operator_product_name", "ImperaOS Operator Panel"),
    ("operatorBundleId", "operator_bundle_id", "com.imperaos.operatorpanel"),
    ("runtimeResourceDir", "runtime_resource_dir", "imperaos-runtime"),
    ("domain", "domain", "imperaos.com"),
    ("repository", "repository", "bakiacikgoz/ImperaOS"),
    ("metricPrefix", "metric_prefix", "imperaos_"),
)


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    """Immutable, typed view of ``branding/identity.json``."""

    display_name: str
    slug: str
    python_distribution: str
    python_package: str
    cli_name: str
    env_prefix: str
    state_root: str
    operator_product_name: str
    operator_bundle_id: str
    runtime_resource_dir: str
    domain: str
    repository: str
    metric_prefix: str

    def to_canonical_dict(self) -> dict[str, str]:
        """Return a fresh mapping using the canonical JSON field names."""

        return {
            json_name: getattr(self, attribute_name)
            for json_name, attribute_name, _expected in _FIELD_SPECS
        }


def load_product_identity(path: str | Path | None = None) -> ProductIdentity:
    """Load and validate the repository's canonical product identity."""

    if path is None:
        packaged_identity = resources.files("imperaos").joinpath("identity.json")
        try:
            identity_text = packaged_identity.read_text(encoding="utf-8")
        except FileNotFoundError:
            identity_text = _CANONICAL_IDENTITY_PATH.read_text(encoding="utf-8")
    else:
        identity_text = Path(path).read_text(encoding="utf-8")
    payload = json.loads(identity_text)
    if not isinstance(payload, dict):
        raise ValueError("product identity must be a JSON object")

    expected_fields = {json_name for json_name, _attribute, _value in _FIELD_SPECS}
    actual_fields = set(payload)
    missing_fields = sorted(expected_fields - actual_fields)
    if missing_fields:
        raise ValueError(f"product identity has missing fields: {missing_fields}")

    unexpected_fields = sorted(actual_fields - expected_fields)
    if unexpected_fields:
        raise ValueError(f"product identity has unexpected fields: {unexpected_fields}")

    non_string_fields = sorted(
        field for field in expected_fields if not isinstance(payload[field], str)
    )
    if non_string_fields:
        raise ValueError(f"product identity fields must be strings: {non_string_fields}")

    values = {field: payload[field] for field in expected_fields}
    mismatched_fields = sorted(
        json_name
        for json_name, _attribute, expected_value in _FIELD_SPECS
        if values[json_name] != expected_value
    )
    if mismatched_fields:
        raise ValueError(
            "product identity fields must match canonical values: "
            f"{mismatched_fields}"
        )

    return ProductIdentity(
        **{
            attribute_name: values[json_name]
            for json_name, attribute_name, _expected in _FIELD_SPECS
        }
    )


PRODUCT_IDENTITY: Final = load_product_identity()

__all__ = ["PRODUCT_IDENTITY", "ProductIdentity", "load_product_identity"]
