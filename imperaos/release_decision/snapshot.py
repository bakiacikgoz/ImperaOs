from __future__ import annotations

from pathlib import Path

from imperaos.release_decision.dossier import verify_release_decision_dossier
from imperaos.release_decision.models import RcReleaseDecisionSnapshot, ReleaseDecisionDossier


def build_rc_release_decision_snapshot(
    *,
    evidence_root: Path,
    profile: str = "enterprise",
) -> RcReleaseDecisionSnapshot:
    _ = profile
    root = Path(evidence_root)
    dossier_path = root / "rc-release-decision" / "release_decision_dossier.json"
    summary_path = root / "rc-release-decision" / "release_decision_summary.md"
    if not dossier_path.exists():
        return RcReleaseDecisionSnapshot(
            status="not_available",
            warnings=["RC_RELEASE_DECISION_MISSING"],
        )
    try:
        dossier = ReleaseDecisionDossier.model_validate_json(
            dossier_path.read_text(encoding="utf-8")
        )
    except Exception:
        return RcReleaseDecisionSnapshot(
            status="blocked",
            latestDossierRef=str(dossier_path).replace("\\", "/"),
            blockingReasons=["RC_RELEASE_DECISION_INVALID"],
        )
    report = verify_release_decision_dossier(
        dossier,
        allow_conditional=True,
        dossier_path=dossier_path,
    )
    status = dossier.status if report.status != "blocked" else "blocked"
    return RcReleaseDecisionSnapshot(
        status=status,
        latestDossierRef=str(dossier_path).replace("\\", "/"),
        latestSummaryRef=str(summary_path).replace("\\", "/") if summary_path.exists() else None,
        signoffStatus=dossier.signoff_status,
        hatAStatus=dossier.hat_a_status,
        hatBStatus=dossier.hat_b_status,
        designPartnerRcStatus=dossier.design_partner_rc_status,
        noShipBlockingCount=dossier.no_ship_register.blocking_count,
        externalBlockerCount=dossier.no_ship_register.external_blocker_count,
        evidenceRefCount=len(dossier.evidence_refs),
        blockingReasons=sorted(set(dossier.blocking_reasons + report.blocking_reasons)),
        warnings=sorted(set(dossier.warnings + report.warnings)),
    )
