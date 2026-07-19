from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from imperaos.artifacts.models import ArtifactModel, BoundedId

LicensedArtifactKind = Literal["spreadsheet", "canvas"]
LicenseReasonCode = Literal[
    "ARTIFACT_LICENSE_ENABLED",
    "ARTIFACT_LICENSE_FEATURE_DISABLED",
    "ARTIFACT_LICENSE_EVIDENCE_MISSING",
    "ARTIFACT_LICENSE_EVIDENCE_INVALID",
    "ARTIFACT_LICENSE_EXPIRED",
    "ARTIFACT_LICENSE_MODE_FORBIDDEN",
    "ARTIFACT_LICENSE_VERSION_MISMATCH",
    "ARTIFACT_LICENSE_TARGET_MISMATCH",
    "ARTIFACT_LICENSE_OFFLINE_UNVERIFIED",
    "ARTIFACT_LICENSE_ACTIVATION_UNSUPPORTED",
    "ARTIFACT_LICENSE_PACKAGE_MISSING",
]

EXPECTED_PACKAGES: dict[LicensedArtifactKind, dict[str, str]] = {
    "spreadsheet": {
        "handsontable": "18.0.0",
        "@handsontable/react-wrapper": "18.0.0",
    },
    "canvas": {"tldraw": "5.2.5"},
}
EXPECTED_PRODUCT: dict[LicensedArtifactKind, str] = {
    "spreadsheet": "handsontable",
    "canvas": "tldraw",
}


class ArtifactLicenseCapability(ArtifactModel):
    contract_version: Literal["artifact-license-capability/v1"] = (
        "artifact-license-capability/v1"
    )
    kind: LicensedArtifactKind
    enabled: bool
    reason_code: LicenseReasonCode

    @model_validator(mode="after")
    def validate_enabled_reason(self) -> ArtifactLicenseCapability:
        if self.enabled != (self.reason_code == "ARTIFACT_LICENSE_ENABLED"):
            raise ValueError("artifact license capability reason does not match enabled state")
        return self


class ArtifactLicenseDoctorResult(ArtifactModel):
    contract_version: Literal["artifact-license-doctor-result/v1"] = (
        "artifact-license-doctor-result/v1"
    )
    capability: ArtifactLicenseCapability
    profile: Literal["production"] = "production"
    build_target: str = Field(min_length=1, max_length=128)
    evidence_id: BoundedId | None = None
    checked_packages: dict[str, str]


class _SignedEntitlement(ArtifactModel):
    schema_version: Literal["artifact-license-entitlement/v1"]
    evidence_id: BoundedId
    product: str = Field(min_length=1, max_length=64)
    license_mode: Literal["commercial-production"]
    package_versions: dict[str, str]
    build_targets: tuple[str, ...] = Field(min_length=1, max_length=32)
    offline_permitted: bool
    not_before_utc: datetime
    expires_at_utc: datetime
    activation_mechanism: Literal["offline-secret-reference"]
    activation_verified: bool
    secret_ref: str = Field(pattern=r"^IMPERAOS_LICENSE_[A-Z0-9_]{1,96}$")
    approved_by: BoundedId
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("not_before_utc", "expires_at_utc")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("license entitlement timestamps must include a timezone")
        return value.astimezone(UTC)


def _disabled(
    kind: LicensedArtifactKind,
    reason: LicenseReasonCode,
    *,
    build_target: str,
    evidence_id: str | None = None,
) -> ArtifactLicenseDoctorResult:
    return ArtifactLicenseDoctorResult(
        capability=ArtifactLicenseCapability(kind=kind, enabled=False, reason_code=reason),
        build_target=build_target,
        evidence_id=evidence_id,
        checked_packages=EXPECTED_PACKAGES[kind],
    )


def _canonical_unsigned(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        {key: value for key, value in payload.items() if key != "signature"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def evaluate_artifact_license(
    kind: LicensedArtifactKind,
    *,
    repo_root: Path,
    evidence_path: Path | None,
    build_target: str,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> ArtifactLicenseDoctorResult:
    """Resolve a licensed editor capability without exposing reusable license material."""
    if evidence_path is None or not evidence_path.is_file():
        return _disabled(kind, "ARTIFACT_LICENSE_EVIDENCE_MISSING", build_target=build_target)
    try:
        encoded = evidence_path.read_text(encoding="utf-8")
        raw = json.loads(encoded)
        entitlement = _SignedEntitlement.model_validate_json(encoded)
    except (OSError, json.JSONDecodeError, ValidationError):
        return _disabled(kind, "ARTIFACT_LICENSE_EVIDENCE_INVALID", build_target=build_target)

    evidence_id = entitlement.evidence_id
    if entitlement.product != EXPECTED_PRODUCT[kind]:
        return _disabled(
            kind, "ARTIFACT_LICENSE_MODE_FORBIDDEN", build_target=build_target,
            evidence_id=evidence_id,
        )
    if entitlement.package_versions != EXPECTED_PACKAGES[kind]:
        return _disabled(
            kind, "ARTIFACT_LICENSE_VERSION_MISMATCH", build_target=build_target,
            evidence_id=evidence_id,
        )
    if build_target not in entitlement.build_targets:
        return _disabled(
            kind, "ARTIFACT_LICENSE_TARGET_MISMATCH", build_target=build_target,
            evidence_id=evidence_id,
        )
    if not entitlement.offline_permitted:
        return _disabled(
            kind, "ARTIFACT_LICENSE_OFFLINE_UNVERIFIED", build_target=build_target,
            evidence_id=evidence_id,
        )
    if not entitlement.activation_verified:
        return _disabled(
            kind, "ARTIFACT_LICENSE_ACTIVATION_UNSUPPORTED", build_target=build_target,
            evidence_id=evidence_id,
        )
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if not (entitlement.not_before_utc <= observed_now < entitlement.expires_at_utc):
        return _disabled(
            kind, "ARTIFACT_LICENSE_EXPIRED", build_target=build_target,
            evidence_id=evidence_id,
        )

    secret = (os.environ if environment is None else environment).get(entitlement.secret_ref)
    if not secret:
        return _disabled(
            kind, "ARTIFACT_LICENSE_EVIDENCE_INVALID", build_target=build_target,
            evidence_id=evidence_id,
        )
    expected_signature = hmac.new(
        secret.encode("utf-8"), _canonical_unsigned(raw), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, entitlement.signature):
        return _disabled(
            kind, "ARTIFACT_LICENSE_EVIDENCE_INVALID", build_target=build_target,
            evidence_id=evidence_id,
        )

    package_manifest = repo_root / "apps" / "operator-panel" / "package.json"
    try:
        manifest = json.loads(package_manifest.read_text(encoding="utf-8"))
        installed = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    except (OSError, json.JSONDecodeError):
        installed = {}
    if any(
        installed.get(package) != version
        for package, version in EXPECTED_PACKAGES[kind].items()
    ):
        return _disabled(
            kind, "ARTIFACT_LICENSE_PACKAGE_MISSING", build_target=build_target,
            evidence_id=evidence_id,
        )

    return ArtifactLicenseDoctorResult(
        capability=ArtifactLicenseCapability(
            kind=kind, enabled=True, reason_code="ARTIFACT_LICENSE_ENABLED"
        ),
        build_target=build_target,
        evidence_id=evidence_id,
        checked_packages=EXPECTED_PACKAGES[kind],
    )
