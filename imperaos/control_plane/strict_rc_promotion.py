from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.control_plane.field_evidence import (
    STRICT_BLOCKED_CLAIMS,
    FieldEvidenceVerificationResult,
    OperatorAttestationValidationResult,
    load_field_bundle,
)
from imperaos.memory.models import StrictModel


class StrictRCEvidenceReference(StrictModel):
    path: str
    sha256: str | None = None


class StrictRCPromotionReport(StrictModel):
    schema_version: Literal["control-plane.strict-rc-promotion/v1"] = Field(
        default="control-plane.strict-rc-promotion/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked"]
    ready: bool
    session_id: str = Field(alias="sessionId")
    mode: Literal["rehearsal", "target_environment"]
    target_evidence_status: Literal["pass", "conditional", "blocked", "invalid"] = Field(
        alias="targetEvidenceStatus"
    )
    attestation_status: Literal["valid", "missing", "invalid", "blocked"] = Field(
        alias="attestationStatus"
    )
    claim_guard_status: Literal["pass", "blocked"] = Field(alias="claimGuardStatus")
    governed_workflow_status: str = Field(alias="governedWorkflowStatus")
    support_bundle_status: Literal["present", "missing"] = Field(alias="supportBundleStatus")
    security_baseline_status: Literal["present", "missing"] = Field(alias="securityBaselineStatus")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[StrictRCEvidenceReference] = Field(
        default_factory=list, alias="evidenceRefs"
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


def evaluate_strict_rc_promotion(
    *,
    field_verification: FieldEvidenceVerificationResult,
    attestation: OperatorAttestationValidationResult | None,
    claim_boundaries: dict[str, str],
    governed_workflow_status: str,
    support_bundle_present: bool,
    security_baseline_present: bool,
    now: datetime | None = None,
) -> StrictRCPromotionReport:
    blockers = list(field_verification.blocking_reasons)
    warnings = list(field_verification.warnings)
    if field_verification.mode == "rehearsal":
        warnings.append("TARGET_ENVIRONMENT_REHEARSAL_ONLY")
    if field_verification.status in {"blocked", "invalid"}:
        blockers.append("TARGET_EVIDENCE_VERIFICATION_FAILED")
    if (
        field_verification.raw_persistence
        or field_verification.secret_persistence
        or field_verification.pii_persistence
    ):
        blockers.append("FIELD_EVIDENCE_PRIVACY_PERSISTENCE_DETECTED")
    attestation_status = attestation.status if attestation else "missing"
    if attestation_status == "missing":
        warnings.append("INDEPENDENT_OPERATOR_ATTESTATION_MISSING")
    elif attestation_status != "valid":
        blockers.append("INDEPENDENT_OPERATOR_ATTESTATION_INVALID")
    for claim_id in STRICT_BLOCKED_CLAIMS:
        if claim_boundaries.get(claim_id) not in {"blocked", "deferred"}:
            blockers.append(f"UNSUPPORTED_CLAIM_ALLOWED:{claim_id}")
    if governed_workflow_status != "pass":
        warnings.append("GOVERNED_PILOT_WORKFLOW_NOT_PASS")
    if not support_bundle_present:
        warnings.append("SUPPORT_BUNDLE_MANIFEST_MISSING")
    if not security_baseline_present:
        warnings.append("SECURITY_BASELINE_MISSING")
    ready = (
        not blockers
        and not warnings
        and field_verification.mode == "target_environment"
        and attestation_status == "valid"
    )
    status: Literal["ready", "conditional", "blocked"]
    status = "ready" if ready else "blocked" if blockers else "conditional"
    return StrictRCPromotionReport(
        status=status,
        ready=ready,
        sessionId=field_verification.session_id or "unknown",
        mode=field_verification.mode or "rehearsal",
        targetEvidenceStatus=field_verification.status,
        attestationStatus=attestation_status,
        claimGuardStatus="blocked"
        if any(blocker.startswith("UNSUPPORTED_CLAIM_ALLOWED") for blocker in blockers)
        else "pass",
        governedWorkflowStatus=governed_workflow_status,
        supportBundleStatus="present" if support_bundle_present else "missing",
        securityBaselineStatus="present" if security_baseline_present else "missing",
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        evidenceRefs=[
            StrictRCEvidenceReference(path=ref) for ref in field_verification.evidence_refs
        ],
        generatedAtUtc=now or datetime.now(UTC),
    )


def promote_strict_rc(
    *,
    profile: str,
    field_root: Path,
    rc_root: Path,
    output_root: Path,
    now: datetime | None = None,
) -> StrictRCPromotionReport:
    _ = rc_root
    field_root = Path(field_root)
    output_root = Path(output_root)
    verification_path = field_root / "verification.json"
    attestation_path = field_root / "attestation_validation.json"
    bundle_path = field_root / "target_evidence_bundle.json"
    if verification_path.exists():
        verification = FieldEvidenceVerificationResult.model_validate_json(
            verification_path.read_text(encoding="utf-8")
        )
    else:
        from imperaos.control_plane.field_evidence import verify_field_evidence_bundle

        verification = verify_field_evidence_bundle(bundle_path=bundle_path)
    attestation = None
    if attestation_path.exists():
        attestation = OperatorAttestationValidationResult.model_validate_json(
            attestation_path.read_text(encoding="utf-8")
        )
    _ = profile
    bundle = load_field_bundle(bundle_path)
    claim_boundaries = dict(bundle.claim_boundaries)
    report = evaluate_strict_rc_promotion(
        field_verification=verification,
        attestation=attestation,
        claim_boundaries=claim_boundaries,
        governed_workflow_status=_governed_status(field_root),
        support_bundle_present=(Path("artifacts") / "support_bundle_manifest.json").exists()
        or (field_root / "artifacts" / "support_bundle_manifest.json").exists(),
        security_baseline_present=(Path("artifacts") / "security_posture.json").exists()
        or (field_root / "artifacts" / "security_posture_summary.json").exists(),
        now=now,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_root / "strict_rc_promotion.json", report.model_dump(mode="json", by_alias=True)
    )
    if output_root != field_root:
        _write_json(
            field_root / "strict_rc_promotion.json", report.model_dump(mode="json", by_alias=True)
        )
    return report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def _governed_status(field_root: Path) -> str:
    summary_path = field_root / "artifacts" / "governed_pilot_workflow_summary.json"
    if not summary_path.exists():
        return "missing"
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "invalid"
    return str(payload.get("status") or "missing")
