from __future__ import annotations

from pathlib import Path

from imperaos.release.gate_models import RcGateEvidenceSnapshot
from imperaos.release.gate_verifier import verify_gate_evidence_ledger


def build_rc_gate_evidence_snapshot(
    *,
    evidence_root: Path,
    profile: str = "enterprise",
) -> RcGateEvidenceSnapshot:
    _ = profile
    root = Path(evidence_root)
    ledger_path = root / "release-gates" / "mainline-rc" / "gate_evidence_ledger.json"
    verification_path = root / "release-gates" / "mainline-rc" / "gate_evidence_verification.json"
    if not ledger_path.exists():
        return RcGateEvidenceSnapshot(
            status="missing",
            warnings=["RC_GATE_EVIDENCE_LEDGER_MISSING"],
        )
    report = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=root.parent)
    status = (
        "ready"
        if report.status == "ready"
        else "blocked"
        if report.status == "blocked"
        else "conditional"
    )
    return RcGateEvidenceSnapshot(
        status=status,
        target="mainline-rc",
        latestLedgerRef=str(ledger_path).replace("\\", "/"),
        latestVerificationRef=str(verification_path).replace("\\", "/")
        if verification_path.exists()
        else None,
        verifiedGateCount=report.verified_gate_count,
        missingGateCount=len(report.missing_gate_ids),
        missingArtifactCount=len(report.missing_artifact_ids),
        secretScanStatus="fail" if report.secret_or_raw_findings else "pass",
        rawMarkerScanStatus="fail" if report.secret_or_raw_findings else "pass",
        platform="windows",
        makeRequired=False,
        readyForRcFreeze=report.ready_for_rc_freeze,
        blockingReasons=report.reason_codes if report.status == "blocked" else [],
        warnings=report.reason_codes if report.status != "ready" else [],
    )
