from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidencePlatform(StrEnum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"


class EvidenceStatus(StrEnum):
    PASS = "pass"
    BLOCKED = "blocked"
    FAIL = "fail"


class EvidenceProvider(EvidenceModel):
    name: Literal["ollama", "mock", "none"]
    model: str | None
    strict_json: bool
    synthetic_doctor_passed: bool


class EvidenceBackends(EvidenceModel):
    capture: str
    input: str


class EvidencePermissions(EvidenceModel):
    screen_recording: Literal["granted", "missing", "unknown"]
    accessibility: Literal["granted", "missing", "unknown"]


class EvidenceSafety(EvidenceModel):
    raw_screenshot_persistence: bool
    raw_screenshot_count: int = Field(ge=0)
    sensitive_surface_stop_passed: bool
    approval_snapshot_binding_passed: bool
    semantic_verifier_passed: bool
    replay_verified: bool


class EvidenceClaim(EvidenceModel):
    supervised_live_claim_allowed: bool
    public_live_claim_allowed: bool
    claim_scope: Literal["none", "local_supervised_fixture_only", "supervised_preview"]


class EvidenceIntegrity(EvidenceModel):
    artifact_hash_sha256: str = Field(min_length=64, max_length=64)
    signed: bool
    signature_key_id: str | None


class QualificationEvidence(EvidenceModel):
    schema_version: Literal["computer-use-qualification-evidence/v1"]
    artifact_kind: Literal["computer_use_qualification_evidence"]
    platform: EvidencePlatform
    runtime: Literal["vision-first"]
    suite: str
    status: EvidenceStatus
    reason_codes: list[str]
    generated_at: datetime
    expires_at: datetime
    source_commit: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    provider: EvidenceProvider
    backends: EvidenceBackends
    permissions: EvidencePermissions
    safety: EvidenceSafety
    claim: EvidenceClaim
    integrity: EvidenceIntegrity


@dataclass(frozen=True)
class QualificationEvidenceValidation:
    valid: bool
    status: str
    reason_codes: list[str]
    evidence: QualificationEvidence | None = None


def validate_qualification_evidence(
    payload: object,
    *,
    current_platform: str | None = None,
    current_commit: str | None = None,
    expected_provider: str | None = None,
    expected_model: str | None = None,
    expected_capture_backend: str | None = None,
    expected_input_backend: str | None = None,
    now: datetime | None = None,
    require_commit_match: bool = True,
) -> QualificationEvidenceValidation:
    try:
        evidence = QualificationEvidence.model_validate(payload)
    except ValidationError:
        return QualificationEvidenceValidation(
            valid=False,
            status="invalid",
            reason_codes=["QUALIFICATION_EVIDENCE_SCHEMA_INVALID"],
        )

    reasons = list(evidence.reason_codes)
    reasons.extend(_global_blockers(evidence, now=now))
    if evidence.status == EvidenceStatus.PASS:
        reasons.extend(
            _pass_blockers(
                evidence,
                current_platform=current_platform,
                current_commit=current_commit,
                expected_provider=expected_provider,
                expected_model=expected_model,
                expected_capture_backend=expected_capture_backend,
                expected_input_backend=expected_input_backend,
                require_commit_match=require_commit_match,
            )
        )
    elif require_commit_match and current_commit and evidence.source_commit != current_commit:
        reasons.append("QUALIFICATION_EVIDENCE_COMMIT_MISMATCH")

    invalid_reasons = _invalid_reasons(reasons)
    if invalid_reasons:
        return QualificationEvidenceValidation(
            valid=False,
            status="invalid",
            reason_codes=_unique(invalid_reasons),
            evidence=evidence,
        )
    return QualificationEvidenceValidation(
        valid=True,
        status=evidence.status.value,
        reason_codes=_unique(reasons),
        evidence=evidence,
    )


def _global_blockers(
    evidence: QualificationEvidence,
    *,
    now: datetime | None,
) -> list[str]:
    reasons: list[str] = []
    current_time = now or datetime.now(UTC)
    expires_at = evidence.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < current_time:
        reasons.append("QUALIFICATION_EVIDENCE_STALE")
    if evidence.claim.public_live_claim_allowed:
        reasons.append("PUBLIC_LIVE_CLAIM_NOT_ALLOWED")
    if evidence.safety.raw_screenshot_persistence or evidence.safety.raw_screenshot_count > 0:
        reasons.append("RAW_SCREENSHOT_PERSISTENCE_DETECTED")
    return reasons


def _pass_blockers(
    evidence: QualificationEvidence,
    *,
    current_platform: str | None,
    current_commit: str | None,
    expected_provider: str | None,
    expected_model: str | None,
    expected_capture_backend: str | None,
    expected_input_backend: str | None,
    require_commit_match: bool,
) -> list[str]:
    reasons: list[str] = []
    if current_platform and evidence.platform.value != current_platform:
        reasons.append("QUALIFICATION_EVIDENCE_PLATFORM_MISMATCH")
    if require_commit_match and current_commit and evidence.source_commit != current_commit:
        reasons.append("QUALIFICATION_EVIDENCE_COMMIT_MISMATCH")
    if expected_provider and evidence.provider.name != expected_provider:
        reasons.append("QUALIFICATION_EVIDENCE_PROVIDER_MISMATCH")
    if expected_model and evidence.provider.model != expected_model:
        reasons.append("QUALIFICATION_EVIDENCE_PROVIDER_MISMATCH")
    if expected_capture_backend and evidence.backends.capture != expected_capture_backend:
        reasons.append("QUALIFICATION_EVIDENCE_BACKEND_MISMATCH")
    if expected_input_backend and evidence.backends.input != expected_input_backend:
        reasons.append("QUALIFICATION_EVIDENCE_BACKEND_MISMATCH")
    if not evidence.provider.strict_json or not evidence.provider.synthetic_doctor_passed:
        reasons.append("QUALIFICATION_EVIDENCE_PROVIDER_NOT_VERIFIED")
    if (
        evidence.permissions.screen_recording != "granted"
        or evidence.permissions.accessibility != "granted"
    ):
        reasons.append("QUALIFICATION_EVIDENCE_PERMISSION_MISSING")
    safety = evidence.safety
    if not safety.sensitive_surface_stop_passed:
        reasons.append("SENSITIVE_SURFACE_STOP_NOT_VERIFIED")
    if not safety.approval_snapshot_binding_passed:
        reasons.append("APPROVAL_SNAPSHOT_BINDING_NOT_VERIFIED")
    if not safety.semantic_verifier_passed:
        reasons.append("SEMANTIC_VERIFIER_NOT_VERIFIED")
    if not safety.replay_verified:
        reasons.append("REPLAY_INTEGRITY_NOT_VERIFIED")
    return reasons


def _invalid_reasons(reasons: list[str]) -> list[str]:
    invalid_prefixes = (
        "QUALIFICATION_EVIDENCE_",
        "PUBLIC_LIVE_CLAIM_",
        "RAW_SCREENSHOT_",
        "SENSITIVE_SURFACE_",
        "APPROVAL_SNAPSHOT_",
        "SEMANTIC_VERIFIER_",
        "REPLAY_INTEGRITY_",
    )
    return [
        reason
        for reason in reasons
        if reason.startswith(invalid_prefixes)
    ]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
