from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imperaos.control_plane.models import (
    OperatorAttestation,
    PilotCandidateManifest,
    TargetEvidenceBundle,
)
from imperaos.control_plane.operator_attestation import verify_operator_attestation
from imperaos.control_plane.target_evidence import (
    REQUIRED_BLOCKED_CLAIMS,
    verify_target_evidence_bundle,
)

HANDOFF_DOCS = [
    "docs/DESIGN_PARTNER_TARGET_EVIDENCE_CLOSURE.md",
    "docs/DESIGN_PARTNER_PILOT_CANDIDATE_HANDOFF.md",
    "docs/OPERATOR_ATTESTATION_RUNBOOK.md",
    "docs/PROVIDER_GOVERNANCE_MAINLINE_HANDOFF.md",
]


def generate_design_partner_pilot_candidate_pack(
    *,
    profile: str,
    rc_root: str | Path,
    target_evidence_root: str | Path,
    output_root: str | Path,
) -> PilotCandidateManifest:
    rc = Path(rc_root)
    target = Path(target_evidence_root)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)

    rc_status_path = rc / "design-partner-rc-status.json"
    target_evidence_path = target / "target_evidence_bundle.json"
    attestation_path = target / "operator_attestation.json"
    claim_guard_path = rc / "claim-guard-matrix.json"
    provider_runtime_proof_path = _find_provider_runtime_proof(rc)

    blockers: list[str] = []
    warnings: list[str] = []
    if not rc_status_path.exists():
        blockers.append("RC_STATUS_MISSING")
    else:
        rc_status = _read_json(rc_status_path)
        blockers.extend(str(item) for item in rc_status.get("blockers", []))
        if rc_status.get("status") == "blocked":
            blockers.append("RC_STATUS_BLOCKED")
        elif rc_status.get("status") == "conditional":
            warnings.append("RC_STATUS_CONDITIONAL")

    if not target_evidence_path.exists():
        blockers.append("TARGET_EVIDENCE_BUNDLE_MISSING")
    else:
        bundle = TargetEvidenceBundle.model_validate_json(
            target_evidence_path.read_text(encoding="utf-8")
        )
        verification = verify_target_evidence_bundle(bundle)
        blockers.extend(verification.blocking_reasons)
        if bundle.status == "blocked":
            blockers.extend(bundle.blocking_reasons)
        elif bundle.status == "conditional":
            warnings.extend(bundle.warnings or ["TARGET_EVIDENCE_CONDITIONAL"])

    if attestation_path.exists():
        attestation = OperatorAttestation.model_validate_json(
            attestation_path.read_text(encoding="utf-8")
        )
        attestation_check = verify_operator_attestation(
            attestation,
            required_boundaries=REQUIRED_BLOCKED_CLAIMS,
        )
        blockers.extend(attestation_check.blocking_reasons)
    else:
        warnings.append("OPERATOR_ATTESTATION_MISSING")

    if not provider_runtime_proof_path.exists():
        warnings.append("PROVIDER_RUNTIME_PROOF_MISSING")
    if not claim_guard_path.exists():
        warnings.append("CLAIM_GUARD_MATRIX_MISSING")

    status = "blocked" if blockers else "conditional" if warnings else "pass"
    manifest = PilotCandidateManifest(
        status=status,
        profile=profile,
        rcStatusPath=str(rc_status_path),
        targetEvidencePath=str(target_evidence_path),
        attestationPath=str(attestation_path) if attestation_path.exists() else None,
        providerRuntimeProofPath=str(provider_runtime_proof_path),
        claimGuardPath=str(claim_guard_path),
        handoffDocs=HANDOFF_DOCS,
        blockingReasons=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )
    _write_json(output / "manifest.json", manifest.model_dump(mode="json", by_alias=True))
    _write_summary(output / "PILOT_CANDIDATE_SUMMARY.md", manifest)
    return manifest


def _find_provider_runtime_proof(rc_root: Path) -> Path:
    workflow_root = rc_root / "provider-runtime" / "workflow-proof"
    exact = workflow_root / "read_only_ops_triage_workflow_proof.json"
    if exact.exists():
        return exact
    matches = sorted(workflow_root.glob("*.json"))
    return matches[0] if matches else exact


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "blocked", "blockers": ["INVALID_JSON"]}
    return value if isinstance(value, dict) else {"status": "blocked", "blockers": ["INVALID_JSON"]}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(path: Path, manifest: PilotCandidateManifest) -> None:
    blockers = [f"- {reason}" for reason in manifest.blocking_reasons] or ["- none"]
    warnings = [f"- {warning}" for warning in manifest.warnings] or ["- none"]
    lines = [
        "# Design Partner Pilot Candidate",
        "",
        f"Status: {manifest.status}",
        f"Target evidence: {manifest.target_evidence_path}",
        f"Operator attestation: {manifest.attestation_path or 'missing'}",
        f"Provider runtime proof: {manifest.provider_runtime_proof_path}",
        "",
        "Unsupported claims remain closed: public desktop installer, live computer-use, "
        "and approval-free irreversible mutation.",
        "",
        "Blocking reasons:",
        *blockers,
        "",
        "Warnings:",
        *warnings,
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
