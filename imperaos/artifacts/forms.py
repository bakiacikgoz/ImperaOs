from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import JsonValue, canonical_json

_MAX_RESPONSE_BYTES = 512 * 1024


@dataclass(frozen=True, slots=True)
class _ValidationIssue(Exception):
    reason_code: str
    path: str


def validate_form_response(
    schema: dict[str, JsonValue],
    response: dict[str, JsonValue],
) -> None:
    if len(canonical_json(response).encode("utf-8")) > _MAX_RESPONSE_BYTES:
        _raise_validation("FORM_RESPONSE_TOO_LARGE", "/")
    try:
        _validate(schema, response, schema, ())
    except _ValidationIssue as issue:
        raise ArtifactDomainError(
            ArtifactErrorCode.FORM_VALIDATION_FAILED,
            "form response does not satisfy the governed schema",
            details={"path": issue.path, "reasonCode": issue.reason_code},
        ) from None


def _validate(
    schema: dict[str, JsonValue],
    value: JsonValue,
    root: dict[str, JsonValue],
    path: tuple[str, ...],
    ref_stack: frozenset[str] = frozenset(),
) -> None:
    if len(path) > 64:
        _fail("FORM_RESPONSE_DEPTH_EXCEEDED", path)
    raw_ref = schema.get("$ref")
    if isinstance(raw_ref, str):
        if raw_ref in ref_stack:
            _fail("FORM_SCHEMA_REF_CYCLE", path)
        parts = raw_ref.split("/")
        definitions = root.get(parts[1]) if len(parts) == 3 else None
        target = definitions.get(parts[2]) if isinstance(definitions, dict) else None
        if not isinstance(target, dict):
            _fail("FORM_SCHEMA_REF_UNRESOLVED", path)
        _validate(target, value, root, path, ref_stack | {raw_ref})
        return

    if "const" in schema and not _json_equal(value, schema["const"]):
        _fail("FORM_CONST_MISMATCH", path)
    allowed = schema.get("enum")
    if isinstance(allowed, list) and not any(_json_equal(value, item) for item in allowed):
        _fail("FORM_ENUM_MISMATCH", path)
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for branch in one_of:
            if not isinstance(branch, dict):
                continue
            try:
                _validate(branch, value, root, path, ref_stack)
            except _ValidationIssue:
                continue
            matches += 1
        if matches != 1:
            _fail("FORM_ONE_OF_MISMATCH", path)

    expected_type = schema.get("type")
    if expected_type == "object" or (expected_type is None and isinstance(value, dict)):
        if not isinstance(value, dict):
            _fail("FORM_TYPE_OBJECT_REQUIRED", path)
        properties = schema.get("properties")
        property_schemas = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    _fail("FORM_REQUIRED_FIELD_MISSING", (*path, key))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in property_schemas:
                    _fail("FORM_ADDITIONAL_PROPERTY_DENIED", (*path, key))
        for key, child in property_schemas.items():
            if key in value and isinstance(child, dict):
                _validate(child, value[key], root, (*path, key), ref_stack)
        return
    if expected_type == "array" or (expected_type is None and isinstance(value, list)):
        if not isinstance(value, list):
            _fail("FORM_TYPE_ARRAY_REQUIRED", path)
        _validate_length(schema, len(value), path, "ITEMS")
        if schema.get("uniqueItems") is True:
            encoded = [canonical_json(item) for item in value]
            if len(encoded) != len(set(encoded)):
                _fail("FORM_ARRAY_UNIQUE_REQUIRED", path)
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                _validate(items, item, root, (*path, str(index)), ref_stack)
        return
    if expected_type == "string" or (expected_type is None and isinstance(value, str)):
        if not isinstance(value, str):
            _fail("FORM_TYPE_STRING_REQUIRED", path)
        _validate_length(schema, len(value), path, "LENGTH")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            _fail("FORM_PATTERN_MISMATCH", path)
        _validate_format(schema.get("format"), value, path)
        return
    if expected_type in {"number", "integer"} or (
        expected_type is None and isinstance(value, (int, float)) and not isinstance(value, bool)
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail("FORM_TYPE_NUMBER_REQUIRED", path)
        if expected_type == "integer" and not (
            isinstance(value, int) or (isinstance(value, float) and value.is_integer())
        ):
            _fail("FORM_TYPE_INTEGER_REQUIRED", path)
        _validate_number(schema, value, path)
        return
    if expected_type == "boolean" and not isinstance(value, bool):
        _fail("FORM_TYPE_BOOLEAN_REQUIRED", path)
    if expected_type == "null" and value is not None:
        _fail("FORM_TYPE_NULL_REQUIRED", path)


def _validate_length(
    schema: dict[str, JsonValue],
    observed: int,
    path: tuple[str, ...],
    label: str,
) -> None:
    minimum = schema.get("minLength" if label == "LENGTH" else "minItems")
    maximum = schema.get("maxLength" if label == "LENGTH" else "maxItems")
    if isinstance(minimum, int) and observed < minimum:
        _fail(f"FORM_{label}_MINIMUM", path)
    if isinstance(maximum, int) and observed > maximum:
        _fail(f"FORM_{label}_MAXIMUM", path)


def _validate_number(
    schema: dict[str, JsonValue],
    value: int | float,
    path: tuple[str, ...],
) -> None:
    checks: tuple[tuple[str, Any, bool], ...] = (
        ("minimum", schema.get("minimum"), True),
        ("maximum", schema.get("maximum"), True),
        ("exclusiveMinimum", schema.get("exclusiveMinimum"), False),
        ("exclusiveMaximum", schema.get("exclusiveMaximum"), False),
    )
    for name, boundary, inclusive in checks:
        if not isinstance(boundary, (int, float)) or isinstance(boundary, bool):
            continue
        if name in {"minimum", "exclusiveMinimum"} and (
            value < boundary if inclusive else value <= boundary
        ):
            _fail("FORM_NUMBER_MINIMUM", path)
        if name in {"maximum", "exclusiveMaximum"} and (
            value > boundary if inclusive else value >= boundary
        ):
            _fail("FORM_NUMBER_MAXIMUM", path)
    multiple = schema.get("multipleOf")
    if isinstance(multiple, (int, float)) and multiple > 0:
        quotient = value / multiple
        if abs(quotient - round(quotient)) > 1e-9:
            _fail("FORM_NUMBER_MULTIPLE_OF", path)


def _validate_format(raw_format: JsonValue | None, value: str, path: tuple[str, ...]) -> None:
    if raw_format == "email" and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
        _fail("FORM_FORMAT_EMAIL", path)
    if raw_format == "uuid" and re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        value,
    ) is None:
        _fail("FORM_FORMAT_UUID", path)
    if raw_format == "date":
        try:
            date.fromisoformat(value)
        except ValueError:
            _fail("FORM_FORMAT_DATE", path)
    if raw_format == "date-time":
        date_time_pattern = (
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
        )
        if re.fullmatch(date_time_pattern, value) is None:
            _fail("FORM_FORMAT_DATE_TIME", path)
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _fail("FORM_FORMAT_DATE_TIME", path)
    if raw_format == "hostname" and not _valid_hostname(value):
        _fail("FORM_FORMAT_HOSTNAME", path)
    if raw_format == "ipv4":
        try:
            ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            _fail("FORM_FORMAT_IPV4", path)
    if raw_format == "ipv6":
        try:
            ipaddress.IPv6Address(value)
        except ipaddress.AddressValueError:
            _fail("FORM_FORMAT_IPV6", path)
    if raw_format == "uri-reference" and not _valid_uri_reference(value):
        _fail("FORM_FORMAT_URI_REFERENCE", path)


def _json_equal(left: JsonValue, right: JsonValue) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        return (
            isinstance(left, (int, float))
            and isinstance(right, (int, float))
            and left == right
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return left == right


def _valid_hostname(value: str) -> bool:
    if not value or len(value) > 253:
        return False
    labels = value[:-1].split(".") if value.endswith(".") else value.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is not None
        for label in labels
    )


def _valid_uri_reference(value: str) -> bool:
    if not value or re.search(r"[\x00-\x20\\]", value):
        return False
    try:
        urlsplit(value)
    except ValueError:
        return False
    return True


def _fail(reason_code: str, path: tuple[str, ...]) -> None:
    pointer = "/" + "/".join(
        segment.replace("~", "~0").replace("/", "~1") for segment in path
    )
    raise _ValidationIssue(reason_code, pointer[:512])


def _raise_validation(reason_code: str, path: str) -> None:
    raise ArtifactDomainError(
        ArtifactErrorCode.FORM_VALIDATION_FAILED,
        "form response does not satisfy the governed schema",
        details={"path": path, "reasonCode": reason_code},
    )
