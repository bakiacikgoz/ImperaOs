from __future__ import annotations

from imperaos.control_plane.field_evidence import (
    STRICT_BLOCKED_CLAIMS,
    FieldEvidenceVerificationResult,
    OperatorAttestationValidationResult,
)
from imperaos.control_plane.strict_rc_promotion import evaluate_strict_rc_promotion


def test_strict_rc_promotion_missing_attestation_is_conditional() -> None:
    report = evaluate_strict_rc_promotion(
        field_verification=_verification(),
        attestation=None,
        claim_boundaries={claim: "deferred" for claim in STRICT_BLOCKED_CLAIMS},
        governed_workflow_status="pass",
        support_bundle_present=True,
        security_baseline_present=True,
    )

    assert report.status == "conditional"
    assert "INDEPENDENT_OPERATOR_ATTESTATION_MISSING" in report.warnings


def test_strict_rc_promotion_blocks_claim_overreach() -> None:
    report = evaluate_strict_rc_promotion(
        field_verification=_verification(),
        attestation=_attestation(),
        claim_boundaries={claim: "deferred" for claim in STRICT_BLOCKED_CLAIMS[:-1]},
        governed_workflow_status="pass",
        support_bundle_present=True,
        security_baseline_present=True,
    )

    assert report.status == "blocked"
    assert any(reason.startswith("UNSUPPORTED_CLAIM_ALLOWED") for reason in report.blockers)


def _verification() -> FieldEvidenceVerificationResult:
    return FieldEvidenceVerificationResult(
        sessionId="field-session",
        mode="target_environment",
        status="pass",
        bundleSha256="sha256:bundle",
        itemCount=6,
    )


def _attestation() -> OperatorAttestationValidationResult:
    return OperatorAttestationValidationResult(
        status="valid",
        sessionId="field-session",
        releasePackId="design-partner-rc-v1",
        bundleSha256="sha256:bundle",
    )
