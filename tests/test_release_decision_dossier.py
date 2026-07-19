from __future__ import annotations

from pathlib import Path

from imperaos.release_decision.dossier import (
    build_release_decision_dossier,
    verify_release_decision_dossier,
    write_release_decision_pack,
)
from imperaos.release_decision.models import (
    HumanSignoffVerificationReport,
    NoShipRegister,
    RcFreezeReconciliationReport,
)


def _ready_reconciliation() -> RcFreezeReconciliationReport:
    return RcFreezeReconciliationReport(
        status="ready",
        originalFreezeStatus="conditional",
        reconciledStatus="ready",
        closedConditionalReasons=["REQUIRED_GATE_MISSING:control-plane-gate"],
    )


def test_dossier_conditional_without_signoff() -> None:
    dossier = build_release_decision_dossier(
        profile="enterprise",
        branch="codex/test",
        head_sha="1" * 40,
        reconciliation=_ready_reconciliation(),
        no_ship_register=NoShipRegister(status="clear"),
        signoff_report=HumanSignoffVerificationReport(status="missing"),
        evidence_refs=[],
    )

    assert dossier.status == "conditional"
    assert dossier.signoff_status == "missing"


def test_dossier_false_ready_hard_fails() -> None:
    dossier = build_release_decision_dossier(
        profile="enterprise",
        branch="codex/test",
        head_sha="1" * 40,
        reconciliation=_ready_reconciliation(),
        no_ship_register=NoShipRegister(status="clear"),
        signoff_report=HumanSignoffVerificationReport(status="missing"),
        evidence_refs=[],
    )
    dossier.status = "approved_for_design_partner_rc"

    report = verify_release_decision_dossier(dossier)

    assert report.status == "blocked"
    assert "APPROVED_WITHOUT_VERIFIED_SIGNOFF" in report.blocking_reasons


def test_write_release_decision_pack_outputs_hashes(tmp_path: Path) -> None:
    dossier = build_release_decision_dossier(
        profile="enterprise",
        branch="codex/test",
        head_sha="1" * 40,
        reconciliation=_ready_reconciliation(),
        no_ship_register=NoShipRegister(status="clear"),
        signoff_report=HumanSignoffVerificationReport(status="missing"),
        evidence_refs=[],
    )

    manifest = write_release_decision_pack(dossier, output_root=tmp_path)

    assert (tmp_path / "release_decision_dossier.json").exists()
    assert (tmp_path / "release_decision_summary.md").exists()
    assert manifest["status"] == "conditional"
