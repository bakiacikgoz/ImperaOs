from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.design_partner_rc import (
    build_design_partner_rc_status,
    is_expected_blocked_claim_boundary_alert,
)
from imperaos.control_plane.pilot_operations import build_design_partner_beta_status
from imperaos.control_plane.provider_conformance import run_provider_native_gate
from imperaos.control_plane.provider_runtime_workflows import (
    ProviderWorkflowProofRequest,
    run_provider_workflow_proof,
    workflow_proof_hash,
)
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.control_plane.target_evidence import verify_target_evidence_bundle
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


REQUIRED_OPTIONAL_ARTIFACTS = [
    "external_gateway_smoke.json",
    "policy_pack_promotion.json",
    "evidence_index.json",
    "reports-alerts-logs/manifest.json",
    "control-plane-snapshot.json",
    "claim-guard-matrix.json",
    "design-partner-rc-status.json",
    "DESIGN_PARTNER_RC_REPORT.md",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Design Partner RC release pack.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output", default="artifacts/design-partner-rc")
    parser.add_argument("--state-root", default=CONTROL_PLANE_STATE_ROOT)
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--beta-evidence-root")
    parser.add_argument("--target-evidence-root")
    parser.add_argument("--fail-on-conditional", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = REPO_ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC)
    config = RuntimeConfig.from_profile(args.profile)
    state_root = _resolve_path(args.state_root)
    evidence_root = _resolve_path(args.evidence_root)
    beta_evidence_root = (
        _resolve_path(args.beta_evidence_root) if args.beta_evidence_root else evidence_root
    )
    target_evidence_root = (
        _resolve_path(args.target_evidence_root) if args.target_evidence_root else None
    )

    snapshot = build_control_plane_snapshot(
        root_dir=state_root,
        profile=args.profile,
        evidence_root=evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    claim_matrix = ClaimGuard(config=config).evaluate(evidence_root=evidence_root)
    beta_status = build_design_partner_beta_status(
        evidence_root=beta_evidence_root,
        generated_at=snapshot.generated_at_utc,
    )
    snapshot.design_partner_beta = beta_status
    snapshot.design_partner_rc = build_design_partner_rc_status(
        data_source=snapshot.data_source,
        claims=claim_matrix.model_dump(mode="json"),
        evidence_packs=snapshot.evidence_packs,
        reports=snapshot.reports,
        alerts=snapshot.alerts,
        execution_surfaces=snapshot.execution_surfaces,
        design_partner_beta=beta_status,
        provider_governance=snapshot.provider_governance,
        generated_at=snapshot.generated_at_utc,
    )
    provider_gate = run_provider_native_gate(
        profile=args.profile,
        output_dir=output / "provider-governance",
    )
    workflow_proof = run_provider_workflow_proof(
        ProviderWorkflowProofRequest(
            workflow_kind="read_only_ops_triage",
            provider_kind="openai_responses",
            profile=args.profile,
            runtime_mode="dry_run",
            output_root=output / "provider-runtime" / "workflow-proof",
        )
    )

    _write_json(
        output / "control-plane-snapshot.json",
        snapshot.model_dump(mode="json", by_alias=True),
    )
    _write_json(output / "claim-guard-matrix.json", claim_matrix.model_dump(mode="json"))
    _write_json(
        output / "design-partner-rc-status.json",
        snapshot.design_partner_rc.model_dump(mode="json", by_alias=True),
    )
    _write_text(output / "head_commit.txt", _git(["rev-parse", "HEAD"]))
    _write_text(output / "git_status.txt", _git(["status", "--short"]))

    initial_manifest = {
        "version": "control-plane.design-partner-rc-pack/v1",
        "generatedAtUtc": generated_at.isoformat(),
        "status": "pending",
        "output": _display_path(output),
        "profile": args.profile,
        "stateRoot": _display_path(state_root),
        "evidenceRoot": _display_path(evidence_root),
        "designPartnerRcStatus": snapshot.design_partner_rc.status,
        "blockers": list(snapshot.design_partner_rc.blockers),
        "warnings": list(snapshot.design_partner_rc.warnings),
        "artifacts": [],
        "claimBoundaries": _claim_boundaries(snapshot),
        "evidencePackCount": len(snapshot.evidence_packs),
        "readyReportCount": sum(1 for report in snapshot.reports if report.status == "ready"),
        "activeErrorAlertCount": _active_error_alert_count(snapshot),
        "providerGovernance": _provider_governance_manifest(snapshot, provider_gate),
        "providerWorkflowProof": _provider_workflow_proof_manifest(workflow_proof),
        "targetEvidenceClosure": _target_evidence_manifest(target_evidence_root),
    }
    _write_report(output / "DESIGN_PARTNER_RC_REPORT.md", initial_manifest)

    artifacts = _artifact_status(output)
    artifact_blockers = [
        f"artifact:{item['path']}"
        for item in artifacts
        if item.get("status") in {"blocked", "fail", "failed"}
    ]
    artifact_warnings = [
        f"artifact:{item['path']}"
        for item in artifacts
        if item.get("status") in {"conditional", "missing"}
    ]
    blockers = [*snapshot.design_partner_rc.blockers, *artifact_blockers]
    warnings = [*snapshot.design_partner_rc.warnings, *artifact_warnings]
    target_evidence = _target_evidence_manifest(target_evidence_root)
    if target_evidence.get("status") == "blocked":
        blockers.extend(str(item) for item in target_evidence.get("blockingReasons", []))
    status = (
        "blocked"
        if blockers
        else "conditional"
        if warnings
        else "pass"
    )
    manifest = {
        "version": "control-plane.design-partner-rc-pack/v1",
        "generatedAtUtc": generated_at.isoformat(),
        "status": status,
        "output": _display_path(output),
        "profile": args.profile,
        "stateRoot": _display_path(state_root),
        "evidenceRoot": _display_path(evidence_root),
        "designPartnerRcStatus": snapshot.design_partner_rc.status,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": artifacts,
        "claimBoundaries": _claim_boundaries(snapshot),
        "evidencePackCount": len(snapshot.evidence_packs),
        "readyReportCount": sum(1 for report in snapshot.reports if report.status == "ready"),
        "activeErrorAlertCount": _active_error_alert_count(snapshot),
        "providerGovernance": _provider_governance_manifest(snapshot, provider_gate),
        "providerWorkflowProof": _provider_workflow_proof_manifest(workflow_proof),
        "targetEvidenceClosure": target_evidence,
    }
    _write_json(output / "manifest.json", manifest)
    _write_report(output / "DESIGN_PARTNER_RC_REPORT.md", manifest)
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(f"built {output}")
    if status == "blocked" or (args.fail_on_conditional and status == "conditional"):
        raise SystemExit(1)


def _artifact_status(output: Path) -> list[dict[str, object]]:
    items = []
    for relative in REQUIRED_OPTIONAL_ARTIFACTS:
        path = output / relative
        present = path.exists()
        size = path.stat().st_size if present else 0
        items.append(
            {
                "path": relative,
                "present": present,
                "bytes": size,
                "sourcePath": _display_path(path) if present else None,
                "status": _artifact_payload_status(path) if present and size > 0 else "missing",
            }
        )
    return items


def _artifact_payload_status(path: Path) -> str:
    if path.suffix.lower() != ".json":
        return "present"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "blocked"
    if not isinstance(payload, dict):
        return "present"
    design_partner_rc = payload.get("designPartnerRc")
    if isinstance(design_partner_rc, dict) and isinstance(design_partner_rc.get("status"), str):
        return str(design_partner_rc["status"])
    status = payload.get("status")
    if isinstance(status, str):
        return status
    return "present"


def _write_report(path: Path, manifest: dict[str, object]) -> None:
    provider_governance = manifest.get("providerGovernance")
    provider_status = "unknown"
    provider_gate_status = "unknown"
    if isinstance(provider_governance, dict):
        provider_status = str(provider_governance.get("status", "unknown"))
        provider_gate_status = str(provider_governance.get("gateStatus", "unknown"))
    provider_workflow = manifest.get("providerWorkflowProof")
    workflow_status = "unknown"
    workflow_mutations = "unknown"
    if isinstance(provider_workflow, dict):
        workflow_status = str(provider_workflow.get("status", "unknown"))
        workflow_mutations = str(provider_workflow.get("executedMutations", "unknown"))
    target_evidence = manifest.get("targetEvidenceClosure")
    target_status = "not_requested"
    target_attestation = "missing"
    if isinstance(target_evidence, dict):
        target_status = str(target_evidence.get("status", "not_requested"))
        target_attestation = str(target_evidence.get("attestationStatus", "missing"))
    lines = [
        "# Design Partner RC Report",
        "",
        f"Status: {manifest['status']}",
        f"Generated: {manifest['generatedAtUtc']}",
        f"Profile: {manifest.get('profile')}",
        f"Evidence root: {manifest.get('evidenceRoot')}",
        f"State root: {manifest.get('stateRoot')}",
        "",
        "## Boundary",
        "",
        "- Computer-use live execution remains blocked.",
        "- Public desktop installer claim remains blocked.",
        "- Preview fixtures are not treated as live evidence.",
        "- Provider native checks use offline fixtures only; external live calls remain disabled.",
        "",
        "## Provider Governance",
        "",
        f"- Status: {provider_status}",
        f"- Offline conformance: {provider_gate_status}",
        "",
        "## Provider Workflow Proof",
        "",
        f"- Status: {workflow_status}",
        f"- Executed mutations: {workflow_mutations}",
        "",
        "## Target Evidence Closure",
        "",
        f"- Status: {target_status}",
        f"- Operator attestation: {target_attestation}",
        "",
        "## Artifacts",
        "",
    ]
    for item in manifest["artifacts"]:
        if isinstance(item, dict):
            lines.append(
                f"- {item['path']}: {item.get('status')} "
                f"({'present' if item['present'] else 'missing'}, {item.get('bytes')} bytes)"
            )
    lines.extend(["", "## Warnings", ""])
    warnings = manifest.get("warnings") if isinstance(manifest, dict) else []
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else proc.stderr


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _claim_boundaries(snapshot: object) -> dict[str, str]:
    surfaces = getattr(snapshot, "execution_surfaces", [])
    return {
        "computerUseLive": _surface_status(surfaces, "computer-use"),
        "publicDesktopInstaller": _surface_status(surfaces, "public-desktop-installer"),
    }


def _provider_governance_manifest(snapshot: object, gate: dict[str, object]) -> dict[str, object]:
    provider_governance = getattr(snapshot, "provider_governance", None)
    reports = gate.get("reports", [])
    conformance_artifacts = []
    if isinstance(reports, list):
        for report in reports:
            if isinstance(report, dict):
                conformance_artifacts.append(
                    {
                        "providerKind": report.get("providerKind"),
                        "status": report.get("status"),
                        "path": report.get("evidencePath"),
                        "offline": report.get("offline"),
                    }
                )
    return {
        "status": getattr(provider_governance, "overall_status", "blocked"),
        "gateStatus": gate.get("status", "fail"),
        "contractVersion": getattr(
            provider_governance,
            "contract_version",
            "control-plane.provider-governance/v1",
        ),
        "conformanceArtifacts": conformance_artifacts,
        "blockingReasons": list(getattr(provider_governance, "blocking_reasons", [])),
    }


def _provider_workflow_proof_manifest(workflow_proof: object) -> dict[str, object]:
    artifact_path = Path(str(getattr(workflow_proof, "artifact_path", "")))
    artifact_hash = workflow_proof_hash(artifact_path) if artifact_path.exists() else None
    return {
        "status": getattr(workflow_proof, "status", "unknown"),
        "workflowId": getattr(workflow_proof, "workflow_id", "unknown"),
        "workflowKind": "read_only_ops_triage",
        "executedMutations": getattr(workflow_proof, "executed_mutations", None),
        "approvalTicketsCreated": getattr(workflow_proof, "approval_tickets_created", None),
        "artifactPath": _display_path(artifact_path) if artifact_path.exists() else None,
        "artifactHash": artifact_hash,
        "providerInvocations": list(getattr(workflow_proof, "provider_invocations", [])),
        "evidenceArtifacts": list(getattr(workflow_proof, "evidence_artifacts", [])),
    }


def _target_evidence_manifest(target_evidence_root: Path | None) -> dict[str, object]:
    if target_evidence_root is None:
        return {
            "status": "not_requested",
            "bundlePath": None,
            "attestationStatus": "missing",
            "blockingReasons": [],
            "warnings": [],
        }
    bundle_path = target_evidence_root / "target_evidence_bundle.json"
    attestation_path = target_evidence_root / "operator_attestation.json"
    if not bundle_path.exists():
        return {
            "status": "conditional",
            "bundlePath": str(bundle_path),
            "attestationStatus": "missing",
            "blockingReasons": [],
            "warnings": ["TARGET_EVIDENCE_BUNDLE_MISSING"],
        }
    verification = verify_target_evidence_bundle(bundle_path)
    return {
        "status": "blocked" if verification.status == "blocked" else "pass",
        "bundlePath": str(bundle_path),
        "attestationPath": str(attestation_path) if attestation_path.exists() else None,
        "attestationStatus": "present" if attestation_path.exists() else "missing",
        "blockingReasons": list(verification.blocking_reasons),
        "warnings": list(verification.warnings),
    }


def _surface_status(surfaces: object, surface_id: str) -> str:
    if not isinstance(surfaces, list):
        return "missing"
    for surface in surfaces:
        if getattr(surface, "surface_id", None) == surface_id:
            return str(getattr(surface, "status", "missing"))
    return "missing"


def _active_error_alert_count(snapshot: object) -> int:
    alerts = getattr(snapshot, "alerts", [])
    if not isinstance(alerts, list):
        return 0
    return sum(
        1
        for alert in alerts
        if getattr(alert, "status", None) == "active"
        and getattr(alert, "severity", None) in {"error", "critical"}
        and not is_expected_blocked_claim_boundary_alert(alert)
    )


if __name__ == "__main__":
    main()
