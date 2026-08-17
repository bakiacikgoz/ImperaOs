from __future__ import annotations

import json
from pathlib import Path

from imperaos.release.gate_models import RcEvidenceOrchestrationReport
from imperaos.release.gate_verifier import verify_gate_evidence_ledger


def export_rc_evidence_orchestration(
    *,
    ledger_path: Path,
    output_root: Path,
    repo_root: Path,
) -> RcEvidenceOrchestrationReport:
    output_root.mkdir(parents=True, exist_ok=True)
    verification = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=repo_root)
    verification_path = output_root / "gate_evidence_verification.json"
    verification_path.write_text(
        json.dumps(verification.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report = RcEvidenceOrchestrationReport(
        status=verification.status,
        ledgerPath=str(ledger_path).replace("\\", "/"),
        verificationPath=str(verification_path).replace("\\", "/"),
        readyForRcFreeze=verification.ready_for_rc_freeze,
        blockingReasons=verification.reason_codes if verification.status == "blocked" else [],
        warnings=verification.reason_codes if verification.status != "ready" else [],
    )
    (output_root / "rc_evidence_orchestration_report.json").write_text(
        json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return report
