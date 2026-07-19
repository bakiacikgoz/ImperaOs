from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imperaos.control_plane.pilot_workflow_evidence import (
    find_raw_leaks,
    sha256_file,
)
from imperaos.control_plane.pilot_workflow_models import (
    GovernedPilotWorkflowReport,
    GovernedPilotWorkflowVerification,
)


def verify_governed_pilot_workflow_report(
    report_path: str | Path,
    *,
    strict: bool = True,
) -> GovernedPilotWorkflowVerification:
    path = Path(report_path)
    blocking: list[str] = []
    warnings: list[str] = []
    refs_checked = 0
    workflow_id: str | None = None
    run_id: str | None = None
    report_hash: str | None = None
    raw_leak_detected = False
    unsupported_claim_allowed = False

    if not path.exists():
        return GovernedPilotWorkflowVerification(
            status="fail",
            blockingReasons=["REPORT_MISSING"],
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = GovernedPilotWorkflowReport.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        return GovernedPilotWorkflowVerification(
            status="fail",
            blockingReasons=[f"REPORT_INVALID:{type(exc).__name__}"],
        )

    workflow_id = report.workflow_id
    run_id = report.run_id
    report_hash = sha256_file(path)
    raw_leak_detected = bool(report.raw_leak_detected or find_raw_leaks(payload))
    unsupported_claim_allowed = bool(report.unsupported_claim_allowed)

    if report.status not in {"pass", "conditional"}:
        blocking.append("REPORT_STATUS_NOT_PASSING")
    if report.evidence_mode != "hash_only" or report.raw_persistence:
        blocking.append("EVIDENCE_NOT_HASH_ONLY")
    if raw_leak_detected:
        blocking.append("RAW_LEAK_DETECTED")
    if unsupported_claim_allowed:
        blocking.append("UNSUPPORTED_CLAIM_ALLOWED")
    if report.claim_guard_status == "fail":
        blocking.append("CLAIM_GUARD_FAILED")

    for step in report.steps:
        for component in (step.memory, step.provider, step.approval, step.evidence):
            for ref in component.evidence_refs:
                refs_checked += 1
                ref_path = Path(ref)
                if not ref_path.exists():
                    blocking.append(f"EVIDENCE_REF_MISSING:{ref}")
                    continue
                try:
                    ref_payload: Any = json.loads(ref_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    ref_payload = ref_path.read_text(encoding="utf-8")
                leaks = find_raw_leaks(ref_payload, include_keys=True)
                if leaks:
                    blocking.append(f"EVIDENCE_REF_RAW_LEAK:{ref}")

    if strict and report.evidence_manifest_path:
        manifest_path = Path(report.evidence_manifest_path)
        if not manifest_path.exists():
            blocking.append("EVIDENCE_MANIFEST_MISSING")
        else:
            refs_checked += 1
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                blocking.append("EVIDENCE_MANIFEST_INVALID")
            else:
                if manifest.get("evidenceMode") != "hash_only" or manifest.get("rawPersistence"):
                    blocking.append("EVIDENCE_MANIFEST_NOT_HASH_ONLY")
                for item in manifest.get("items", []):
                    item_path = Path(str(item.get("path") or ""))
                    if not item_path.exists():
                        blocking.append(f"EVIDENCE_MANIFEST_ITEM_MISSING:{item_path}")

    status = "fail" if blocking else "pass"
    return GovernedPilotWorkflowVerification(
        status=status,
        workflowId=workflow_id,
        runId=run_id,
        reportHash=report_hash,
        evidenceRefsChecked=refs_checked,
        rawLeakDetected=raw_leak_detected,
        unsupportedClaimAllowed=unsupported_claim_allowed,
        blockingReasons=sorted(set(blocking)),
        warnings=warnings,
    )


def export_governed_pilot_workflow_report(
    report_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    path = Path(report_path)
    verification = verify_governed_pilot_workflow_report(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    export = {
        "schemaVersion": "control-plane.governed-pilot-workflow-export/v1",
        "status": verification.status,
        "reportHash": verification.report_hash,
        "verification": verification.model_dump(mode="json", by_alias=True),
        "report": payload,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": verification.status,
        "outputPath": str(output),
        "reportHash": verification.report_hash,
    }
