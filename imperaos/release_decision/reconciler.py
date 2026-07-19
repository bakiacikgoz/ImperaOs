from __future__ import annotations

import json
from pathlib import Path

from imperaos.release.gate_verifier import verify_gate_evidence_ledger
from imperaos.release_decision.models import (
    RcFreezeReconciliationInput,
    RcFreezeReconciliationReport,
)
from imperaos.release_decision.scanner import load_evidence_ref, scan_file


def build_reconciliation_input(
    *,
    gate_ledger_path: Path,
    freeze_manifest_path: Path,
    repo_root: Path,
    profile: str = "enterprise",
) -> RcFreezeReconciliationInput:
    return RcFreezeReconciliationInput(
        gateLedgerRef=load_evidence_ref(gate_ledger_path, kind="gate_ledger", repo_root=repo_root),
        freezeManifestRef=load_evidence_ref(
            freeze_manifest_path,
            kind="freeze_manifest",
            repo_root=repo_root,
        ),
        repoRoot=str(repo_root),
        profile=profile,
    )


def reconcile_rc_freeze(input: RcFreezeReconciliationInput) -> RcFreezeReconciliationReport:
    repo_root = Path(input.repo_root)
    gate_ledger_path = repo_root / input.gate_ledger_ref.path
    freeze_manifest_path = repo_root / input.freeze_manifest_ref.path
    findings = scan_file(gate_ledger_path) + scan_file(freeze_manifest_path)
    if findings:
        return RcFreezeReconciliationReport(
            status="blocked",
            originalFreezeStatus="unknown",
            reconciledStatus="blocked",
            blockingReasons=findings,
            evidenceRefs=[input.gate_ledger_ref, input.freeze_manifest_ref],
        )
    gate_report = verify_gate_evidence_ledger(ledger_path=gate_ledger_path, repo_root=repo_root)
    freeze_payload = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    ledger_payload = json.loads(gate_ledger_path.read_text(encoding="utf-8"))
    original_status = str(freeze_payload.get("status", "missing"))
    warnings = [str(item) for item in freeze_payload.get("warnings", [])]
    blockers = [str(item) for item in freeze_payload.get("blockers", [])]
    missing_gate_warnings = [
        item for item in warnings if item.startswith("REQUIRED_GATE_MISSING:")
    ]
    closed = [
        item
        for item in missing_gate_warnings
        if item.split(":", 1)[1] not in gate_report.missing_gate_ids
    ]
    remaining = [item for item in warnings if item not in closed]
    blocking_reasons = list(blockers)
    if gate_report.status != "ready":
        blocking_reasons.extend(
            gate_report.reason_codes or [f"GATE_LEDGER_{gate_report.status.upper()}"]
        )
        blocking_reasons.extend(str(item) for item in ledger_payload.get("blockingReasons", []))
    if gate_report.tampered_artifact_refs:
        blocking_reasons.append("ARTIFACT_HASH_MISMATCH")
    if gate_report.secret_or_raw_findings:
        blocking_reasons.append("RAW_OR_SECRET_MARKER_FOUND")
    if blocking_reasons:
        status = "blocked"
        reconciled = "blocked"
    elif remaining:
        status = "conditional"
        reconciled = "conditional"
    else:
        status = "ready"
        reconciled = "ready"
    return RcFreezeReconciliationReport(
        status=status,
        originalFreezeStatus=original_status,
        reconciledStatus=reconciled,
        closedConditionalReasons=closed,
        remainingConditionalReasons=remaining,
        blockingReasons=sorted(set(blocking_reasons)),
        warnings=[item for item in gate_report.warnings if item not in blocking_reasons],
        evidenceRefs=[input.gate_ledger_ref, input.freeze_manifest_ref],
    )


def missing_reconciliation(reason: str) -> RcFreezeReconciliationReport:
    return RcFreezeReconciliationReport(
        status="blocked",
        originalFreezeStatus="missing",
        reconciledStatus="blocked",
        blockingReasons=[reason],
    )
