from __future__ import annotations

from pathlib import Path

from imperaos.release.gate_models import RcEvidenceBackfillReport
from imperaos.release.gate_verifier import verify_gate_evidence_ledger


def build_rc_evidence_backfill_report(
    *,
    gate_ledger_path: Path,
    repo_root: Path,
    missing_gate_ids: list[str],
) -> RcEvidenceBackfillReport:
    verification = verify_gate_evidence_ledger(ledger_path=gate_ledger_path, repo_root=repo_root)
    if verification.status == "blocked":
        return RcEvidenceBackfillReport(
            status="blocked",
            readyForRcFreeze=False,
            missingGateIds=missing_gate_ids,
            blockingReasons=verification.reason_codes,
        )
    unresolved = [item for item in missing_gate_ids if item in verification.missing_gate_ids]
    resolved = [item for item in missing_gate_ids if item not in unresolved]
    ready = verification.ready_for_rc_freeze and not unresolved
    return RcEvidenceBackfillReport(
        status="ready" if ready else "conditional",
        readyForRcFreeze=ready,
        resolvedGateIds=resolved,
        missingGateIds=unresolved,
        warnings=verification.warnings,
    )
